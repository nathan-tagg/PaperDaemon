# Tasks

Tests run on their own port and their own data folder (`PAPERDAEMON_HOME` in a temporary folder), never on
port 8770 or the user's data.

## 1. Settings

- [x] 1.1 Add the inbox notebook (a path, default "PaperDaemon inbox"), the system prompt tag (default "sprompt") and the trigger tag defaulting to the app's name to the tablet settings, refuse empty values and tags that match, and verify a save and reload keeps them (unit test)
- [x] 1.2 Unit-test defaults, merging over an older file, every validation message, and the atomic save; `uv run pytest` passes

## 2. Secrets

- [x] 2.1 Unit-test storing, replacing, removing and checking secrets against an in-memory keyring backend, and verify `settings.json` never contains a saved key
- [x] 2.2 Unit-test that a pasted `@ByteArray(...)` device token is stored without the wrapper and that removing the token ends the cloud session

## 3. Local API

- [x] 3.1 Move every route under `/api/v1/` and point the UI at it; verify `/api/settings` answers 404 and `/api/v1/settings` answers with the settings
- [x] 3.2 Test the pairing check: 401 with no token and with a wrong token, 200 with the right one, 401 for the old token after a rotation, 404 for `/docs` and `/openapi.json`
- [x] 3.3 Verify with a captured log that a session of API calls never writes the pairing token or any secret Done: `tests/test_secrets.py` (a session of calls, a wrong token and a stored key: neither the token nor the key in any log record or any file of the data folder).

## 4. Desktop shell

- [x] 4.1 Start PaperDaemon on a test port in both modes; verify the window opens only after the API answers, and that `--headless` opens no window and serves paired requests Done: `tests/test_headless.py` (headless serves paired requests, refuses unpaired ones, loads no window); the window opens after `server.wait_up` (`__main__.py`), and the desktop app is the Tauri shell, which starts the engine with `--announce` and waits for its READY line.

## 5. Tablet connection and sync

- [x] 5.1 Make trash invisible: every library listing and reader skips documents in the trash; verify with a unit test on a mirror fixture holding a trashed notebook
- [x] 5.2 Make rollback report later changes to the document and wait for confirmation; verify with a unit test against a stubbed cloud tree
- [x] 5.3 Unit-test that pulled page lists keep PaperDaemon's unpushed pages and take the tablet's order for the rest

## 6. Real-run evidence

- [ ] 6.1 With a device token registered for PaperDaemon itself (never the desktop app's token while the pipeline runs), a fresh data folder and a test port: check the connection, run the full pull, change a page on the tablet, and confirm the notification arrives and the next pull fetches only that document. Record file and byte counts here.
