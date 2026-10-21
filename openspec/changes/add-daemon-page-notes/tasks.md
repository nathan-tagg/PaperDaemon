# Tasks: add-daemon-page-notes

## 1. Settings

- [x] 1.1 `daemon.retries` (0 to 5, default 0) and `daemon.page_notes` (default off)
- [x] 1.2 `daemon.layer` (default "Daemon"), shown on the Settings screen while notes are on
- [x] 1.3 Their labels and help in every language

## 2. The notes

- [x] 2.1 Lettered in the band above the safe area, signed, with a retry box when a job is left
- [x] 2.2 The daemon's author id, in the page's author table; ids counted in `daemon-ink.json`
- [x] 2.3 Every write erases everything of his, including copies the page never saw, and his old notes
- [x] 2.4 One layer per page at the bottom of the list, sent whole with every note; made anew if deleted
- [x] 2.5 A tick in the retry box found where the tablet draws it, anchored groups included

## 3. The account of the work

- [x] 3.1 "On it" from the daemon as soon as the job is handed over
- [x] 3.2 The host's events: what it read, its plan, each step as it ends; each goes up as a note
- [x] 3.3 The last note, in the page itself, with how the job ended

## 4. Reading

- [x] 4.1 The renderer and the fingerprint leave his strokes out; the user's strokes on his layer are read
- [x] 4.2 Handwriting mapped from the render's own origin, not the frame scaled

## 5. Retries

- [x] 5.1 A failed job goes back in the queue while the settings allow, told how the last try ended
