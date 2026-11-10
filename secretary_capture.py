"""Background Google Meet caption capture for Hermes Secretary.

Runs Playwright in a dedicated thread (sync API) so Hermes tool handlers can
return quickly. Transcript/state are kept in-memory with a lock and can be
persisted to the plugin data dir.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class CaptionSegment:
    speaker: Optional[str]
    text: str
    ts: float
    source: str = "google_meet_captions"


@dataclass
class CaptureState:
    status: str = "idle"  # idle|starting|joining|capturing|stopping|stopped|error
    meet_code: Optional[str] = None
    meet_url: Optional[str] = None
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    error: Optional[str] = None
    segments: list[dict[str, Any]] = field(default_factory=list)
    last_seen: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["segment_count"] = len(self.segments)
        # Keep status payload small; full transcript via get_transcript.
        d.pop("segments", None)
        return d


class MeetCaptureManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = CaptureState()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._context = None
        self._page = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._state.to_dict()

    def transcript(self, limit: Optional[int] = None) -> dict[str, Any]:
        with self._lock:
            segs = list(self._state.segments)
            if limit is not None:
                segs = segs[-int(limit) :]
            return {
                "ok": True,
                "meet_code": self._state.meet_code,
                "status": self._state.status,
                "segments": segs,
                "segment_count": len(self._state.segments),
            }

    def start(
        self,
        meet_code_or_url: str,
        *,
        headless: bool = False,
        guest_name: Optional[str] = None,
    ) -> dict[str, Any]:
        meet_code = _normalize_meet_code(meet_code_or_url)
        meet_url = f"https://meet.google.com/{meet_code}"
        with self._lock:
            if self._state.status in {"starting", "joining", "capturing"}:
                return {"ok": False, "error": "Capture already running", "status": self.status()}
            self._state = CaptureState(
                status="starting",
                meet_code=meet_code,
                meet_url=meet_url,
                started_at=time.time(),
            )
            self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            args=(meet_code, meet_url, headless, guest_name),
            name=f"hermes-secretary-{meet_code}",
            daemon=True,
        )
        self._thread.start()
        return {"ok": True, "message": "Capture starting in background", "status": self.status()}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._state.status not in {"starting", "joining", "capturing"}:
                return {"ok": True, "message": "No active capture", "status": self.status()}
            self._state.status = "stopping"
        self._stop_event.set()
        return {"ok": True, "message": "Stop requested", "status": self.status()}

    def save_transcript(self, data_dir: Path) -> Optional[Path]:
        data_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "meet_code": self._state.meet_code,
                "meet_url": self._state.meet_url,
                "status": self._state.status,
                "started_at": self._state.started_at,
                "stopped_at": self._state.stopped_at,
                "segments": list(self._state.segments),
            }
            code = self._state.meet_code or "unknown"
        name = f"transcript-{code}-{int(time.time())}.json"
        out = data_dir / name
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (data_dir / "transcript-latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return out

    # ---- thread worker ----
    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self._state, k, v)

    def _append(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            if text == self._state.last_seen:
                return
            self._state.last_seen = text
            self._state.segments.append(asdict(CaptionSegment(speaker=None, text=text, ts=time.time())))

    def _run(self, meet_code: str, meet_url: str, headless: bool, guest_name: Optional[str] = None) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            self._set(status="error", error=f"Playwright not available: {e}. Install plugin deps and run: playwright install chromium")
            return

        # Throwaway browser profile: guest joins keep no session or cookies.
        profile_dir = tempfile.mkdtemp(prefix="hermes-secretary-")
        try:
            with sync_playwright() as p:
                self._set(status="joining")
                context = p.chromium.launch_persistent_context(
                    profile_dir,
                    headless=headless,
                    viewport={"width": 1280, "height": 720},
                    args=["--no-sandbox", "--disable-setuid-sandbox"] if headless else [],
                )
                self._context = context
                page = context.pages[0] if context.pages else context.new_page()
                self._page = page
                page.goto(meet_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                _handle_join_screen(page, guest_name)
                _mute_av(page)
                _try_enable_captions(page)
                self._set(status="capturing")
                self._capture_loop(page)
                context.close()
        except Exception as e:
            self._set(status="error", error=str(e))
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
            self._context = None
            self._page = None
            with self._lock:
                if self._state.status not in {"error"}:
                    self._state.status = "stopped"
                self._state.stopped_at = time.time()

    def _capture_loop(self, page) -> None:
        # Google Meet caption DOM changes often; try several selectors.
        selectors = [
            '[data-caption-text]',
            '[aria-live="polite"]',
            '.a4cQT',  # common caption container class (unstable)
            '.iTTPOb',
            '[jsname="tgaKEf"]',
        ]
        while not self._stop_event.is_set():
            found = False
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    count = loc.count()
                    if count > 0:
                        # Read visible caption nodes; keep last few.
                        texts = []
                        for i in range(max(0, count - 4), count):
                            try:
                                t = loc.nth(i).inner_text(timeout=500).strip()
                                if t:
                                    texts.append(t)
                            except Exception:
                                pass
                        if texts:
                            merged = " ".join(texts)
                            self._append(merged)
                            found = True
                            break
                except Exception:
                    pass
            if not found:
                # Fallback: broad caption region scan (cheap heuristic)
                try:
                    text = page.evaluate(
                        """() => {
                          const els = Array.from(document.querySelectorAll('[aria-live], [role="region"]'));
                          const hit = els.find(e => /caption|subtitle/i.test((e.getAttribute('aria-label')||'') + ' ' + (e.className||'')));
                          return hit ? (hit.innerText||'').trim() : '';
                        }"""
                    )
                    if text:
                        self._append(text)
                except Exception:
                    pass
            page.wait_for_timeout(1500)


def _normalize_meet_code(value: str) -> str:
    v = (value or "").strip()
    if "meet.google.com/" in v:
        v = v.split("meet.google.com/", 1)[1]
    v = v.replace("meet/", "").split("?", 1)[0].split("#", 1)[0].strip("/")
    return v


def _fill_guest_name(page, guest_name: str) -> None:
    # Anonymous (not signed in) joiners must enter a display name first.
    for sel in ('input[aria-label*="name" i]', 'input[placeholder*="name" i]', 'input[type="text"]'):
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.fill(guest_name, timeout=3000)
                return
        except Exception:
            pass


def _handle_join_screen(page, guest_name: Optional[str] = None) -> None:
    # Best-effort: selectors vary by locale/UI version.
    if guest_name:
        _fill_guest_name(page, guest_name)
    candidates = [
        'button:has-text("Join now")',
        'button:has-text("Ask to join")',
        'button:has-text("Ask to be let in")',
        '[aria-label*="Join now"]',
        '[aria-label*="Ask to join"]',
        '[data-idom-class*="join"]',
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                loc.click(timeout=3000)
                page.wait_for_timeout(2000)
                return
        except Exception:
            pass


def _mute_av(page) -> None:
    for label_sub in ("Turn off microphone", "Turn off camera", "microphone", "camera"):
        try:
            loc = page.locator(f'[aria-label*="{label_sub}"]').first
            if loc.is_visible(timeout=1000):
                # Only click "turn off" style controls; avoid toggling on.
                aria = (loc.get_attribute("aria-label") or "").lower()
                if "turn off" in aria or "mute" in aria:
                    loc.click(timeout=1500)
        except Exception:
            pass


def _try_enable_captions(page) -> None:
    for sel in (
        'button[aria-label*="captions" i]',
        'button[aria-label*="Turn on captions" i]',
        '[aria-label*="subtitle" i]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                aria = (loc.get_attribute("aria-label") or "").lower()
                if "turn on" in aria or "off" in aria and "captions" in aria:
                    loc.click(timeout=1500)
                    page.wait_for_timeout(1000)
                    return
        except Exception:
            pass
