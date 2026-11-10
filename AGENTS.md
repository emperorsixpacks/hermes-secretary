# AGENTS.md

Hermes Agent plugin that joins Google Meet in a persistent browser profile and scrapes live captions. Python + Playwright is the shipped implementation; `src/` is a TypeScript prototype.

## Commands

```bash
bash setup.sh                  # install deps, playwright chromium, symlink plugin, create ./secret
pip install -e .               # python deps (playwright>=1.40)
python3 -m playwright install chromium
hermes plugins enable hermes-secretary
hermes secretary install       # runs setup.sh via the CLI
hermes secretary accounts
hermes secretary add-account work          # opens browser to sign in; do this once per account
npx tsx join-meet.ts <meet-code-or-url> --account=work   # local TS joiner (real entrypoint)
```

There is no test suite wired up. `package.json` scripts reference `vite`, which is not a dependency — treat them as stale. `src/joiner.test.ts` is a Playwright Test file with no runner script.

## Architecture

- `hermes_secretary_plugin.py` — pip entrypoint shim only; re-exports `register` from `__init__.py`. On import failure it raises `RuntimeError` and `capabilities()` returns `[]`.
- `__init__.py` — real `register(ctx)`, all tool schemas and handlers. `pyproject.toml` lists `hermes_secretary_plugin`, `secretary_capture`, `secretary_cli` as top-level `py-modules`, so these are **not** a package.
- `secretary_capture.py` — `MeetCaptureManager`, `CaptureState`, `CaptionSegment`. Owns the Playwright thread.
- `secretary_cli.py` — `hermes secretary` subcommands (`install`, `accounts`, `add-account`).
- `src/` — TS prototype (`SecretaryPlugin`, `CaptureAdapter`); not used by the Python plugin.

## Hermes tools (toolset `hermes-secretary`)

`secretary_join_meet` (alias `secretary_start_capture`), `secretary_stop_capture`, `secretary_get_transcript`, `secretary_status`, `secretary_list_accounts`.

- `secretary_join_meet` returns immediately; capture runs in a background daemon thread. Poll `secretary_status` / `secretary_get_transcript`.
- `secretary_join_meet` only supports `capture_source=google_meet_captions` (the `whisper_local` enum value is not implemented and is rejected).
- `secretary_get_transcript` and `secretary_stop_capture` persist JSON to the Hermes plugin data dir when `save` is set / on stop.

## Accounts and profiles

- Each account gets `./secret/<account>/` as a persistent Chromium profile (gitignored).
- Account names are sanitized with `[^a-zA-Z0-9._@-]+` → `-`.
- Legacy quirk: account `"default"` maps to the repo-root `./secret` itself when that dir contains `Default`/`Local State`/`Preferences` and no `./secret/default`.
- Sign in once with `headless=false`; headless sign-in generally fails.

## Transcript output

Written as `transcript-<account>-<code>-<epoch>.json`, `transcript-<account>-latest.json`, and `transcript-latest.json`.

## Pitfalls

- Caption scraping depends on brittle Google Meet selectors (`[data-caption-text]`, `.a4cQT`, `[jsname="tgaKEf"]`, etc.); expect breakage when Meet's DOM changes.
- Only use on meetings you are authorized to join/record.
- `join-meet.mjs` is a stub that only prints usage; use `join-meet.ts` via `npx tsx`.
- Platform support is declared Linux/macOS only.
