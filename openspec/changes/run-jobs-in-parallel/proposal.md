# Proposal: run-jobs-in-parallel

## Why

PaperDaemon works one job at a time. For lineups whose models are a cloud API or a command-line program, nothing on
this computer limits how many calls run at once, and a page waits behind every other page for no reason. The
maintainer (11-16): "for cli and api calls, every job should execute in parallel", limited to one per notebook ("so
multiple notebooks can be worked on at a time"), "but only one local job at a time". This is the 0.3.0 release.

## What Changes

- Jobs on different notebooks run at the same time, each in a process of its own; a notebook has at most one job
  running, and its next page waits for it.
- A LOCAL job -- one whose lineup's text model runs on this computer's graphics card -- runs only when no other local
  job runs, in either library (the Mirror and the False Mirror). Every other job is never held by another job; a
  picture it asks of a model on the card takes its turn on the card, one picture at a time.
- The engine answers each model call, picture and search for the lineup of the job that asked, not for one lineup
  "in use" (two jobs on two lineups no longer change each other's models).
- A job's work reaches the tablet when that job is recorded, and nothing of another job still running goes with it:
  the notebooks other jobs are working, and the documents they made, wait for their own job.
- Stopping a job (Abandon) ends that job alone; what it wrote and the documents it made are put back; the other jobs
  run on.
- The window shows every job being worked: a progress bar on each notebook being worked, and each in the job list.
- An update waits for every job in progress.

## Impact

- `paperdaemon/settings.py`, `paperdaemon/server.py`, `paperdaemon/card.py`: the lineup of each request.
- `paperdaemon/pipeline/host/`: a dispatcher that starts one worker process per job, the local rule, files of its
  own for each job (pictures read, progress), the lineup named on every call to the engine, the documents it made.
- `paperdaemon/pipeline/daemon/`: several jobs in flight, one per notebook; each one's notes, finish and push.
- `paperdaemon/remarkable/sync.py`: the push that holds back other jobs' work; abandon by the job's own documents.
- `paperdaemon/loop.py`, `paperdaemon/ledger.py`: jobs in progress, the queue with several working.
- `paperdaemon/ui/tablet.js`, `paperdaemon/ui/jobs.js`: several progress bars, several jobs working.
