# Proposal: add-false-mirror

## Why

A user without a tablet or an account cannot try PaperDaemon today, and a user with one has nowhere to
work on pages that never go to the tablet. A false mirror is a local library that PaperDaemon treats
exactly as it treats the mirror of the tablet's library, except that it never reaches the cloud: the
daemon answers its pages, the host writes to them, and the page editor makes them.

## What Changes

- The rail's Tablet tab (planned as Library) is named **Mirror**.
- A hidden setting: when the user stays on the Settings screen for a full minute, a **False Mirror**
  setting fades in at the bottom. Its button opens a dialog that explains what a false mirror is; on
  confirming, PaperDaemon creates one.
- A **False Mirror** tab appears in the rail directly below Mirror, the same screen as Mirror over the
  local library.
- The daemon and the host work on the false mirror's pages exactly as on the tablet's: tags, sprompts,
  the queue, notes, jobs. Nothing of it is pulled or pushed.
- For now the page editor's controls appear only on false-mirror pages.

## Impact

- `paperdaemon/ui/strings/*.xml`: the tab is Mirror in every language (done).
- `paperdaemon/loop.py`: a second daemon and host pair for the false mirror, with its own mirror and data
  folders and the cloud turned off.
- `paperdaemon/remarkable/sync.py`: a local-only mirror neither pulls nor pushes.
- `paperdaemon/ui/settings.js`, `app.js` and the Mirror screen: the hidden setting, the dialog, the tab.
- The page editor (`add-page-editor`) joins the app in the false mirror first.
