# Proposal: add-risks-acknowledgment

## Why

PaperDaemon is a third-party application. It signs in with the reMarkable desktop app's login and writes to the
user's notebooks. The maintainer wants every user to read those risks and acknowledge them before using it, and to
say plainly that PaperDaemon is not reMarkable's and that he is not responsible for what anyone does with it.

## What Changes

- RISKS.md in the repository: the risks of using PaperDaemon, in the maintainer's words.
- A setting, `risks.acknowledged`, off until the user acknowledges the risks.
- The window asks first. Until the risks are acknowledged it shows a dialog that cannot be dismissed: it links
  RISKS.md on GitHub and says PaperDaemon is a third-party application, not made or endorsed by reMarkable, meant to
  make an unmodified tablet more useful, and that its author is not responsible for what anyone does with it.
  Acknowledging saves the setting, and the window carries on to setup or its screens.

## Impact

- Affected specs: engine/desktop-shell.
- Code: paperdaemon/settings.py, paperdaemon/ui/app.js, paperdaemon/ui/core.js, the interface strings in every
  language, RISKS.md.
