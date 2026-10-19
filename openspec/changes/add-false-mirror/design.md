# Design: add-false-mirror

## Context

Each daemon and host pair is started with its mirror and data folders in its environment
(`loop.environment`: `RM_MIRROR`, `RM_CACHE`, `RM_STATE`), and everything reaches the tablet through
`sync.push_pending`, which the benchmark already turns off (`RM_HOST_DRY_DOCS=1`). The benchmark also
proves a pair can run on folders of its own without touching the user's library or ledger.

## Decisions

- **D1. A false mirror is a second pair.** The supervisor starts a second daemon and host for the false
  mirror, with `mirror` = the data folder's `false-mirror`, its own state folder, the same settings and
  lineups, and a local-only switch. One pair per mirror keeps every module that reads "the mirror"
  unchanged: each process only ever sees one.
- **D2. Local-only.** With the switch on, nothing is pulled and nothing is pushed: `push_pending` returns
  nothing, the notifier is not started, and the daemon learns of changes by looking at the mirror's own
  files on its interval. Everything else, the ledger, the queue, the jobs, the notes, is the same code.
- **D3. The pages are the tablet's.** A false mirror holds what a real mirror holds: `.metadata`,
  `.content`, `.pagedata` and `.rm` pages in the tablet's frames, written by the editor and by jobs
  through the same library functions, so a page made there is a page the tablet could open.
- **D4. The hidden setting.** The Settings screen counts the time it has been on screen without a
  break; at 60 seconds a False Mirror setting fades in at the bottom, slowly and quietly. Leaving the
  screen resets the count. Once a false mirror exists, the setting shows at once and offers to delete
  it: a dialog says that its notebooks are on this computer only and will be gone, and only on
  confirmation are its pair stopped, its folders removed and its tab taken out of the rail. The setting
  then goes back to Create False Mirror; on a later visit it is hidden behind the minute again.
- **D5. The dialog** says, in plain words, that a false mirror is a library that lives only on this
  computer, that PaperDaemon's daemon answers its pages exactly as it answers the tablet's, and that
  nothing in it reaches the cloud or the tablet. Confirm creates it; cancel leaves nothing behind.
- **D6. The tab.** False Mirror sits directly below Mirror in the rail and is the Mirror screen over the
  false mirror's library.
- **D7. Editing lives here.** The page editor's controls show only on false-mirror pages. It is on
  purpose: like the false mirror itself, editing stays out of sight until a user goes looking.

- **D8. The false mirror's own controls,** none of them in the tablet's mirror: New notebook (in the
  Paper Pro frame), New page, Import and Export, named as the reMarkable apps name them. Import is one
  button whose dialog holds its settings, and lands in the folder open. A long press selects a notebook,
  and its menu (Export, Move, Delete, as on the tablet) slides down from the top over the screen without
  pushing anything. Export writes a PDF, drawn by PaperDaemon's renderer. Tags are set on folders,
  notebooks and pages here, since a false mirror has no tablet to set them on.
- **D9. One queue.** Both mirrors' jobs share the one queue and run one at a time, so the two pairs never
  load the same model at once; the Queue and Notes say which mirror a job is from.

- **D10. The false mirror goes first.** Editing, tagging, import, export, move and delete stay in the
  false mirror until the maintainer judges them safe for the tablet's library; extending them to the
  Mirror tab is then a change of its own.

## Open

- Whether there can be more than one false mirror (one, for now).
- New folder, and what the import dialog's settings are.
