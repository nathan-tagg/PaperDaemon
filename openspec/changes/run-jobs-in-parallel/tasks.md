# Tasks

## 1. The engine

- [x] 1.1 The lineup of each request: `X-PD-Lineup` set for that request alone, read first by `settings.active`
- [x] 1.2 The model wanted next kept per lineup (card.load / status)
- [x] 1.3 Memories applied under a lock (two jobs of one lineup at once)

## 2. The host

- [x] 2.1 The dispatcher: one worker process per job, one per notebook, the local rule across both libraries (D1, D2)
- [x] 2.2 The worker: one job, the lineup on every request, temporary pictures and progress of its own (D3, D4)
- [x] 2.3 The documents a job makes recorded (D6)

## 3. The daemon

- [x] 3.1 Several jobs in flight, one per notebook; notes, finish, restart and conflict handling per job (D5)
- [x] 3.2 The push after a job holds back the other jobs' notebooks and documents (D6)

## 4. Abandon, updates, the window

- [x] 4.1 Abandon ends that job's worker alone; removes the documents it made (D6, D7)
- [x] 4.2 An update waits for every job in progress
- [x] 4.3 `/progress` a list; a bar on each cover being worked; the job list with several working (D8)

## 5. Tests and a real run

- [x] 5.1 Tests: per-request lineup, dispatch rules (notebook, local), push hold, abandon of one job
- [ ] 5.2 A real run in the False Mirror: two notebooks on cloud or command-line lineups worked at once, each page
      right; a local lineup's jobs one at a time
