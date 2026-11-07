# Proposal: add-mirror-library-actions

## Why

The maintainer: the Mirror is missing the + button the False Mirror has, and if editing is allowed on the Mirror it
should have it; right-clicks and long presses do nothing in the Mirror either. Since the Mirror's pages became
editable (add-editable-mirror), its library is the only part of it that still cannot be changed from PaperDaemon:
the + menu, importing, selecting and the selection's actions were built for the False Mirror alone, and the
Mirror's engine refuses every library change.

## What Changes

- With Mirror editing on, the Mirror's library screen offers what the False Mirror's does: the + menu (Quick
  sheets, New notebook, New folder, Import), files dropped on the screen imported into the folder open, and a long
  press or a right-click selecting a notebook or folder, with the selection's actions.
- Each change reaches the tablet through reMarkable's cloud, as PaperDaemon's page edits do: what is new is pushed;
  what changes an item already on the tablet is checked against the cloud first (never written over a change the
  tablet made since it was read) and the item is backed up before PaperDaemon first changes it.
- With Mirror editing off the Mirror's library stays as it is now, with none of these actions.

## Impact

- `paperdaemon/ui/tablet.js` (the library screen's + menu, dropping and selecting, for the Mirror with editing on).
- `paperdaemon/server.py` and `paperdaemon/remarkable/local.py` (the library's actions answered by the Mirror's engine
  when editing is on, each followed by its push), `paperdaemon/remarkable/sync.py` (new items, changes and deletes
  pushed; the cloud check).
- Needs a real run on the maintainer's tablet before release: every action changes his tablet's own library.
