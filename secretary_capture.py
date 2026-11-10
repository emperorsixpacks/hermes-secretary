"""Background Google Meet caption capture for Hermes Secretary.

Runs Playwright in a dedicated thread (sync API) so Hermes tool handlers can
return quickly. Transcript/state are kept in-memory with a lock and can be
persisted to the plugin data dir.
"""

from __future__ import annotations

import getpass
import html
import json
import os
import shutil
import socket
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
        display_name = (guest_name or "").strip() or default_display_name()
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
                    args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
                    + (["--no-sandbox", "--disable-setuid-sandbox"] if headless else []),
                )
                self._context = context
                context.add_init_script(_virtual_camera_script(render_avatar_svg(display_name)))
                page = context.pages[0] if context.pages else context.new_page()
                self._page = page
                page.goto(meet_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                _debug_shot(page, "1-landing")
                _handle_join_screen(page, display_name)
                page.wait_for_timeout(3000)
                _debug_shot(page, "2-after-join-click")
                outcome, detail = self._wait_for_admission(page)
                _debug_shot(page, f"3-{outcome}")
                if outcome != "joined":
                    self._set(status="error", error=detail)
                    context.close()
                    return
                _mute_av(page)
                _try_enable_captions(page)
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

    def _wait_for_admission(self, page, timeout_s: float = 180.0) -> tuple[str, str]:
        """Wait until we are really inside the call. Returns (outcome, detail).

        outcome: joined | blocked | denied | timeout | stopped
        """
        blocked_markers = ("can't join this video call", "cannot join this video call", "unable to join")
        denied_markers = ("denied your request", "you were denied", "removed from the meeting", "meeting has ended", "call has ended")
        deadline = time.time() + timeout_s
        self._set(status="waiting_for_admission")
        while time.time() < deadline:
            if self._stop_event.is_set():
                return "stopped", "Stopped before joining"
            try:
                if page.locator('button[aria-label*="Leave call" i]').first.is_visible(timeout=500):
                    self._set(status="capturing")
                    return "joined", ""
                body = (page.inner_text("body", timeout=2000) or "").lower()
            except Exception:
                body = ""
            if any(m in body for m in blocked_markers):
                return "blocked", (
                    "Google Meet refused the join (\"You can't join this video call\"). The meeting does not allow "
                    "anonymous guests or was not admitted by the host; set the meeting access to Open or have the host invite/admit the bot."
                )
            if any(m in body for m in denied_markers):
                return "denied", "The host denied the request or the meeting ended."
            time.sleep(2)
        return "timeout", f"Not admitted to the meeting within {int(timeout_s)}s (waiting for the host to admit the bot)."

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


def default_display_name() -> str:
    """Bot display name: "<username>'s Secretary" (hostname if no username)."""
    for getter in (getpass.getuser, socket.gethostname):
        try:
            name = (getter() or "").strip()
            if name:
                return f"{name}'s Secretary"
        except Exception:
            pass
    return "Hermes Secretary"


_AVATAR_PATH = Path(__file__).resolve().parent / "assets" / "avatar.svg"
_FALLBACK_AVATAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480"><rect width="640" height="480" fill="#111827"/>'
    '<text x="320" y="250" fill="#f8fafc" font-size="40" font-family="sans-serif" text-anchor="middle">{{NAME}}</text></svg>'
)


def render_avatar_svg(name: str) -> str:
    try:
        svg = _AVATAR_PATH.read_text(encoding="utf-8")
    except Exception:
        svg = _FALLBACK_AVATAR
    return svg.replace("{{NAME}}", html.escape(name))


def _virtual_camera_script(svg: str) -> str:
    """Init script: getUserMedia(video) returns a canvas stream showing the avatar SVG."""
    return """
(() => {
  const md = navigator.mediaDevices;
  if (!md || !md.getUserMedia) return;
  const W = 640, H = 480;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  const img = new Image();
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(%s);
  const draw = () => { try { ctx.drawImage(img, 0, 0, W, H); } catch (e) {} };
  img.onload = draw;
  setInterval(draw, 200);
  const orig = md.getUserMedia.bind(md);
  md.getUserMedia = async (c) => {
    if (c && c.video) {
      const stream = canvas.captureStream(10);
      if (c.audio) {
        try { (await orig({ audio: c.audio })).getAudioTracks().forEach(t => stream.addTrack(t)); } catch (e) {}
      }
      return stream;
    }
    return orig(c);
  };
})();
""" % json.dumps(svg)


def _debug_shot(page, label: str) -> None:
    """If HERMES_SECRETARY_DEBUG_DIR is set, save a screenshot there (join debugging)."""
    d = os.environ.get("HERMES_SECRETARY_DEBUG_DIR")
    if not d:
        return
    try:
        Path(d).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(d) / f"{label}.png"))
    except Exception:
        pass


def _fill_guest_name(page, guest_name: str) -> None:
    # Anonymous (not signed in) joiners must enter a display name first.
    # NB: Locator.is_visible() ignores timeouts, so wait for the field explicitly.
    for sel in ('input[aria-label*="name" i]', 'input[placeholder*="name" i]', 'input[type="text"]'):
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=10000)
            loc.click(timeout=3000)
            loc.fill(guest_name, timeout=3000)
            if loc.input_value() != guest_name:
                loc.fill("")
                loc.press_sequentially(guest_name, delay=40)
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
            loc.wait_for(state="visible", timeout=4000)
            loc.click(timeout=3000)
            page.wait_for_timeout(2000)
            return
        except Exception:
            pass


def _mute_av(page) -> None:
    # Mute the mic only; the camera stays on to show the avatar image.
    for label_sub in ("Turn off microphone", "microphone"):
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
