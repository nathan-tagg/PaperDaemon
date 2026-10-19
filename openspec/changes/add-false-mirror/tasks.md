# Tasks

## 1. Names

- [x] 1.1 The rail's Tablet tab is Mirror in all 19 languages (`tablet.label`)

## 2. The local-only mirror

- [x] 2.1 A local-only switch: `push_pending` and pulls do nothing, the notifier is not started, the daemon watches the mirror's files on its interval. Check: unit tests with a fixture mirror; nothing touches the network Done: `paths.local_only()` (RM_LOCAL_ONLY=1); every cloud call (`sync._call`, `put_blob`, the notifier, the sign-in) raises `LocalOnly`; `mirrored()` is true from the start. tests/test_false_mirror.py
- [x] 2.2 The supervisor starts a second daemon and host for the false mirror, with its own mirror and state folders, and stops them with the first. Check: a test that the two pairs never read each other's folders Done: `loop.fm_environment`, roles fm-daemon and fm-host; without a login only the false mirror's pair runs. The false mirror's daemon, run alone on a throwaway folder, queued a page written in a tagged folder one second later and touched nothing of the cloud.
- [x] 2.3 Creating a false mirror: its folders and a first notebook Done: `<data>/false-mirror` (the library, a sibling of `mirror`) and `<data>/false-mirror-state`; POST/DELETE /false-mirror; the false mirror's own engine (`--false-mirror PORT`) behind /fm/...
- [x] 2.4 One job at a time across the mirrors Done: `paths.one_job()`, a lock the hosts take around each job

## 3. The window

- [x] 3.1 The hidden setting: 60 seconds on Settings, then False Mirror fades in at the bottom; at once when one exists
- [x] 3.2 The dialog that explains it, in every language; once it exists, the setting deletes it behind a confirming dialog (the pair stopped, the folders removed, the tab gone)
- [x] 3.3 The False Mirror tab below Mirror, the Mirror screen over the false mirror's library
- [x] 3.4 The page editor's controls on false-mirror pages only
- [x] 3.5 New notebook, New page, Import (a dialog with its settings, landing in the open folder) and Export (a PDF), placed with the screen's own controls Done: New folder too, for Move to have somewhere to go; Export saves into Downloads
- [x] 3.6 Long press selects a notebook; Export, Move and Delete slide down over the top of the screen without moving anything Done: Tags in the same menu; folders select too
- [x] 3.7 Tags set and removed on folders, notebooks and pages, written as the tablet writes them
- [x] 3.8 One queue for both mirrors, one job at a time, each job marked with its mirror
- [x] 3.9 The tablet gear retired: its settings in Settings, one set for every tablet; the False Mirror's decompose inbox under the Mirror's, and Send to Tablet lands in both
- [x] 3.10 Import made easy, and EPUBs: the chooser at once (several files), or files dropped on the screen; an EPUB laid out by Microsoft Edge (part of Windows; the EPUB libraries that lay out pages are AGPL) at the Paper Pro's size and filed as the tablet files a book

Checked by a headless walk through the real window on a throwaway data folder: the minute's wait, create, the tab,
new notebook and folder, the long press (nothing moved), tags, export, move, the editor (a stroke and typed text saved
to the page file), a page tag and a new page, delete.

## 4. Proof

- [ ] 4.1 A real run: a tagged page made in the false mirror is answered by the real host and models, and nothing reaches the cloud
