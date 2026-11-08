<p align="center">
  <img src="assets/logo.svg" alt="Hermes Secretary logo" width="720" />
</p>

# Hermes Secretary
**Google Meet secretary for Hermes Agent**

Join meetings with tagged account profiles, capture live captions asynchronously, and return transcripts to the agent.

**License:** MIT · **Built for:** Hermes Agent · **Capture:** Google Meet live captions · **Profiles:** Multi-account (`./secret/<account>/`) · **Runtime:** Python + Playwright · **Prototype:** TypeScript/Node

Tagged profiles · async background capture · transcript tools · `hermes secretary` CLI · plugin-native integration

> **Status:** early prototype. Caption scraping is best-effort because Google Meet's DOM/selectors change frequently. Use only for meetings you are authorized to join and follow applicable consent, recording, and transcription rules.

## Features

- **Hermes-native plugin** — `plugin.yaml` + `register(ctx)` entrypoint, tools, CLI command, and session cleanup hook.
- **Async/background capture** — tool handlers return immediately; Playwright capture runs in a dedicated background thread.
- **Multi-account profiles** — each account tag gets its own persistent browser profile under `./secret/<account>/` (plugin-relative, gitignored). Sign in once per account, then reuse it.
- **Google Meet join flow** — best-effort handling for join/lobby controls, A/V mute, caption enablement, and live caption scraping.
- **Transcript persistence** — transcripts can be saved to the Hermes plugin data directory as timestamped JSON plus latest-per-account snapshots.
- **Local test runners** — includes a TypeScript/Playwright runner for quick local join/caption experiments.

## Requirements

- Hermes Agent (for plugin install/enable/tool/CLI integration)
- Linux or macOS
- Python 3.10+
- Playwright (Python) + Chromium browser binary
- Node.js (optional, only for the local TypeScript runner/prototype)

## Install (Hermes)

From a published Git repository:

```bash
hermes plugins install OWNER/hermes-secretary
hermes plugins enable hermes-secretary
# restart Hermes session/gateway so tools/CLI load
```

For local development from this directory:

```bash
mkdir -p ~/.hermes/plugins
ln -sfn "$(pwd)" ~/.hermes/plugins/hermes-secretary
hermes plugins enable hermes-secretary
# restart Hermes session/gateway so tools/CLI load
```

Hermes handles Python dependency consent/admission for the plugin's declared dependencies (`playwright`). Playwright's Chromium browser binary still needs to be installed once:

```bash
hermes secretary install
```

## Add Google accounts (sign in once per tag)

Hermes Secretary stores browser profiles under:

```text
./secret/<account>/
```

This path is relative to the plugin directory and **gitignored** because it contains Google session/profile data.

Add an account tag and sign in:

```bash
hermes secretary add-account work
hermes secretary add-account personal
hermes secretary accounts
```

`add-account` opens a headed browser profile. Sign into the Google account you want for that tag, then close the window. First-time sign-in must be headed (not `--headless`).

## Usage

### Hermes CLI

```bash
hermes secretary install
hermes secretary add-account work
hermes secretary accounts
```

### Hermes tools

Hermes Secretary registers these tools:

| Tool | Purpose |
|---|---|
| `secretary_list_accounts` | List available account/profile tags under the secret root. |
| `secretary_join_meet` | Join a Meet URL/code as an account and start background caption capture. |
| `secretary_start_capture` | Alias of `secretary_join_meet`. |
| `secretary_status` | Show current capture state, account, meeting, segment count, and errors. |
| `secretary_get_transcript` | Return captured caption segments; optionally save to plugin data dir. |
| `secretary_stop_capture` | Stop active capture and persist transcript. |

Example flow:

```text
secretary_list_accounts {}
secretary_join_meet {"meet":"https://meet.google.com/abc-defg-hij","account":"work","headless":false}
secretary_status {}
secretary_get_transcript {"limit": 50, "save": true}
secretary_stop_capture {}
```

Notes:
- `headless=false` is recommended for first-time sign-in or when debugging the join UI.
- `secretary_join_meet` returns immediately; poll `secretary_status` / `secretary_get_transcript`.
- A successful join requires the meeting to be active and the selected account to be invited/admitted.

### Local standalone runner

```bash
cd /path/to/hermes-secretary
npm install
npx tsx join-meet.ts https://meet.google.com/abc-defg-hij --account=work
```

This uses the same plugin-relative `./secret/<account>/` profile layout for local testing.

## Configuration

Plugin config keys (`plugin.yaml`):

| Key | Default | Description |
|---|---|---|
| `secret_dir` | `./secret` | Secret/profile root (relative to plugin dir or absolute). Each account uses `<secret_dir>/<account>/`. |
| `default_account` | *(unset)* | Optional default account tag when `secretary_join_meet` is called without `account`. |
| `headless` | `false` | Run browser headless. Use `false` for first-time Google sign-in/debugging. |
| `capture_source` | `google_meet_captions` | Capture adapter. `whisper_local` is planned but not implemented yet. |

## Project layout

```text
.
├── assets/
│   └── logo.svg
├── plugin.yaml                # Hermes plugin manifest
├── __init__.py                # Hermes register(ctx), tools, hooks, CLI registration
├── capture.py                 # Background Playwright caption capture manager
├── cli.py                     # `hermes secretary` / standalone helper CLI
├── hermes_secretary_plugin.py # Pip entrypoint helper
├── join-meet.ts               # Local TS/Playwright join runner
├── src/                       # Early TS prototype/capture adapter experiments
├── setup.sh                   # Convenience local setup helper
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── README.md
```

## Security & privacy

- **Keep `./secret/` private.** It contains browser session/profile data for signed-in Google accounts. It is gitignored; never commit, upload, or share it.
- **Use authorized meetings only.** Do not join meetings without permission.
- **Respect consent and policy.** Captions/transcripts may be sensitive; follow applicable laws, platform rules, and organizational policies.
- **Treat transcripts as sensitive data.** Saved transcript JSON may contain meeting content.

## Limitations

- Google Meet UI selectors and join/caption behavior can change without notice.
- Caption quality depends on Google Meet's live captions (lossy, language/accent dependent, imperfect with overlapping speakers).
- Speaker attribution is currently best-effort/minimal.
- Whisper/audio-tap capture is planned but not implemented as a production path yet.

## Development

```bash
# Python compile check
python3 -m py_compile __init__.py capture.py cli.py hermes_secretary_plugin.py

# Local setup helper
./setup.sh
./setup.sh --with-node
```

## License

MIT — see [LICENSE](LICENSE).
