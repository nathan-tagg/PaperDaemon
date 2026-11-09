# Proposal: remember-the-window

## Why

Every start, and so every update, opens PaperDaemon's window at a fixed size in the middle of the main screen, on the
Overview. The user keeps it on another monitor, at another size, open on the False Mirror's Dogfood folder, and puts it
back by hand after each update.

## What Changes

- The shell remembers the window's position, size and whether it was maximized, and opens the window there next time.
  A remembered place that is on no screen any more (a monitor unplugged) is ignored.
- The UI remembers the screen it was showing and, for the two library screens, the folder it was in, and opens there
  next time when nothing else (a link, a window made on a new card) says where to open.

## Impact

- Affected specs: engine/desktop-shell (two requirements added).
- Code: shell/src/main.rs (the placement file beside the shell's own data), paperdaemon/ui/app.js (the screen),
  paperdaemon/ui/tablet.js (the folder).
