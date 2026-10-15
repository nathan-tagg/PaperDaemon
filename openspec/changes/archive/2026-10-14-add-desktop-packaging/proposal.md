# Proposal

## Why

PaperDaemon is meant to be published and installed by people who never open a terminal. It needs an
installer, a way to keep running in the background while the tablet is in use, and updates the user
controls. A survey of desktop platforms (`docs/research/desktop-platform.md`) recommends a shell and a
way to package the Python engine.

## What Changes

- An installer for Windows that installs for the current user without administrator rights, with macOS
  and Linux packages to follow.
- PaperDaemon keeps running in the tray when its window is closed, so the daemon keeps working, and quits
  from the tray.
- Starting at login and checking for updates are both off until the user turns them on.
- Signed builds, so the operating system does not warn against them.
- Uninstalling leaves the user's data unless the user asks to remove it.

## Capabilities

### New Capabilities
- `packaging/desktop`: installing, running in the tray, starting at login, updating, signing and
  uninstalling.

### Modified Capabilities
None.

## Non-goals

- Bundling model servers or model files.
- An app store listing.

## Impact

- Build tooling for the chosen shell and for freezing the Python engine.
- A signing setup for release builds.
