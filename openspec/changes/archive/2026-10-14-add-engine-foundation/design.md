# Design

## Context

See proposal.md for why. PaperDaemon starts from a working prototype, the pipeline, which proved the pipeline
but grew as scripts on one machine: it reads the reMarkable desktop app's cache, keeps settings in
environment variables and JSON files next to the code, and serves an unauthenticated studio page
guarded by an address allowlist. PaperDaemon keeps the pipeline and replaces that scaffolding. The code for
most of this change already exists in `paperdaemon/` (settings, vault, server, desktop, remarkable/auth,
remarkable/sync); this change specifies it, and the tasks close the gaps.

## Goals / Non-Goals

**Goals:**
- One engine process that owns everything: settings, secrets, the mirror, and later the daemon and host.
- One API that every client uses, safe to expose on a WireGuard address.
- A shell thin enough that changing the desktop platform later costs a day, not a rewrite.

**Non-Goals:**
- Multi-user or multi-tablet support: one engine serves one reMarkable account.
- Remote access over the open internet: WireGuard (or the loopback address) is the transport.

## Decisions

**A Python engine behind a local HTTP API, and a thin native shell.** The pipeline worth keeping (the
decomposer, the host, the page reader, the `.rm` handling) is Python, so the engine is Python. The UI
talks to it only over HTTP, which is also how a future phone app will talk to it over WireGuard.
*Alternatives:* an all-in-one Electron or Tauri app with the pipeline as a sidecar. That is the same
shape with more moving parts; it stays open as the packaging answer, since the shell is thin either way.

**FastAPI and uvicorn for the API.** Small, typed routes, and middleware for the pairing check.
*Alternative:* the standard library's `http.server`, as the pipeline used. It works, but every route
re-implements parsing and errors, and there is no middleware to put the pairing check in once.

**The pairing token is required from localhost too.** The API writes to the tablet and drives the
GPU. Trusting loopback would let any local process, or a web page in a browser that aims requests at
127.0.0.1, act as the user. A bearer header also defeats cross-site request forgery, because a browser
will not add it to a cross-origin request without a CORS approval the engine never gives.
*Alternative:* trust loopback and require the token only from other addresses (the pipeline's allowlist
model). Rejected for the reasons above.

**Bind only to the addresses the user lists.** 127.0.0.1 always, plus explicit addresses such as the
WireGuard interface, one server per address. *Alternative:* bind 0.0.0.0 and filter by source address,
as the pipeline's studio does. Binding narrowly means an unlisted interface never sees the port at all.

**Secrets in the OS credential store via `keyring`.** *Alternative:* an encrypted file with a key
derived from a password. That adds a password prompt to every start and, when the password is saved
for convenience, protects nothing. The OS store is what the user's other apps already trust.

**PaperDaemon keeps its own mirror and prefers a device token of its own.** the pipeline read the desktop app's
cache, which went stale whenever the app was closed and tied the pipeline to the app. PaperDaemon's own sync
client (ported from the pipeline's `rm_cloud`) removes that dependency. A device token of PaperDaemon's own also
gives it its own change-notification connection: the cloud allows one per device, and a second client
on the same device silently takes it. The README offers the desktop app's token as a second option and
spells out this cost.

**The store's immutability is the safety net.** The cloud's store is content-addressed: an upload never
overwrites, and moving the root pointer never deletes what the old root named. Every write records the
old root first (`root-undo.jsonl`), writes are compare-and-swap on the library generation, and rollback
swaps one document's line in the current tree, so other documents keep whatever the tablet did since.

**The desktop shell is pywebview for now.** It shows the UI in the system's web view (WebView2 on
Windows) with no browser and no bundled Chromium. The platform survey in
`docs/research/desktop-platform.md` decides whether it stays; the spec is written so any shell that
opens a native window on the local UI satisfies it.

**The pairing token reaches the window in the URL fragment.** The window opens
`http://127.0.0.1:<port>/#pair=<token>`. Browsers never send the fragment to the server, and the UI moves
it into session storage and clears the address at once.

## Risks / Trade-offs

- [The reMarkable sync API is unofficial and can change] → All cloud calls live in
  `paperdaemon/remarkable/`; failures surface as plain errors in the tablet settings; the undo log makes a
  bad write recoverable.
- [No credential store on a headless Linux box without a Secret Service] → `keyring` fails loudly and
  PaperDaemon says what to install; see Open Questions.
- [Reusing the desktop app's token makes the two clients fight over the notification connection] → The
  README recommends PaperDaemon's own device token and explains the consequence of the other option.
- [The first pull of a large library can take a long time and gigabytes of disk] → It runs in the
  background with progress in files and bytes; later pulls fetch only changed files.
- [A rollback can undo the user's own later edits to the same document] → The rollback checks for later
  changes and asks first (spec: tablet/sync).

## Migration Plan

None. PaperDaemon starts empty and never touches the pipeline's files or the desktop app's cache.

## Open Questions

Can wait (no effect on these specs or tasks):
- Whether closing the window quits PaperDaemon or leaves the engine running in the tray. This belongs with
  add-desktop-packaging.
- What to do on a headless Linux machine with no credential store.
- Whether pywebview stays as the shell, once the platform survey is reviewed.
