# Tasks

## 1. The engine

- [x] 1.0 The first of them, built ahead of the rest when the maintainer asked for notebooks made on his tablet
      (11-11): POST /library/notebook on the Mirror's engine with Mirror editing on, the notebook in a folder, with
      its tags, sent to the tablet at once (push_new_doc); refused with editing off

- [x] 1.1 The library's actions (notebook, folder, quick sheets, import, the selection's move, delete, tags and
      covers) answered by the Mirror's engine when Mirror editing is on, refused as now when it is off
- [x] 1.2 Each followed by its push: a new item with push_new_doc, a changed one with push_doc after the cloud
      check, a deleted one as the tablet deletes it; a backup of an item before PaperDaemon first changes it
- [x] 1.3 Tests: each action on a throwaway Mirror with the cloud stood in for, refused with editing off

## 2. The window

- [x] 2.1 The Mirror's library screen with editing on: the + menu, files dropped to import, a long press and a
      right-click selecting, the selection's bar
- [x] 2.2 None of them with editing off

- [x] 2.3 While anything is selected, a plain click opens the notebook or folder and lets the selection go (the
      maintainer, 11-16: "if I try to left click it should just open the notebook"); Ctrl or Shift and a click, a
      right-click or a long press adds one or takes it away -- in both libraries

## 3. A real run

- [ ] 3.1 With the maintainer, on his tablet: a folder and a notebook made, a PDF imported, an item moved and one
      deleted, each seen on the tablet
