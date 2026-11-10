# AGENTS.md

Hermes Agent plugin that joins Google Meet in a persistent browser profile and scrapes live captions. Python + Playwright is the shipped implementation; `src/` is a TypeScript prototype.

## Commands

```bash
bash setup.sh                  # install deps, playwright chromium, symlink plugin
pip install -e .               # python deps (playwright>=1.40)
python3 -m playwright install chromium
hermes plugins enable hermes-secretary
hermes secretary install       # runs setup.sh via the CLI
npx tsx join-meet.ts <meet-code-or-url>   # local TS joiner (real entrypoint)
```

There is no test suite wired up. `package.json` scripts reference `vite`, which is not a dependency — treat them as stale. `src/joiner.test.ts` is a Playwright Test file with no runner script.

## Architecture

- `hermes_secretary_plugin.py` — pip entrypoint shim only; re-exports `register` from `__init__.py`. On import failure it raises `RuntimeError` and `capabilities()` returns `[]`.
- `__init__.py` — real `register(ctx)`, all tool schemas and handlers. `pyproject.toml` lists `hermes_secretary_plugin`, `secretary_capture`, `secretary_cli` as top-level `py-modules`, so these are **not** a package.
- `secretary_capture.py` — `MeetCaptureManager`, `CaptureState`, `CaptionSegment`. Owns the Playwright thread.
- `secretary_cli.py` — `hermes secretary` subcommands (`install`).
- `src/` — TS prototype (`SecretaryPlugin`, `CaptureAdapter`); not used by the Python plugin.

## Hermes tools (toolset `hermes-secretary`)

`secretary_join_meet` (alias `secretary_start_capture`), `secretary_stop_capture`, `secretary_get_transcript`, `secretary_status`.

- `secretary_join_meet` returns immediately; capture runs in a background daemon thread. Poll `secretary_status` / `secretary_get_transcript`.
- `secretary_join_meet` only supports `capture_source=google_meet_captions` (the `whisper_local` enum value is not implemented and is rejected).
- `secretary_get_transcript` and `secretary_stop_capture` persist JSON to the Hermes plugin data dir when `save` is set / on stop.

## Profiles

- No sign-in: Google blocks automated sign-in, so the bot joins as a guest (`guest_name`) and the host must admit it.
- Each capture uses a throwaway Chromium profile in a temp dir, deleted afterwards.

## Transcript output

Written as `transcript-<code>-<epoch>.json` and `transcript-latest.json`.

## Pitfalls

- Caption scraping depends on brittle Google Meet selectors (`[data-caption-text]`, `.a4cQT`, `[jsname="tgaKEf"]`, etc.); expect breakage when Meet's DOM changes.
- Only use on meetings you are authorized to join/record.
- `join-meet.mjs` is a stub that only prints usage; use `join-meet.ts` via `npx tsx`.
- Platform support is declared Linux/macOS only.
