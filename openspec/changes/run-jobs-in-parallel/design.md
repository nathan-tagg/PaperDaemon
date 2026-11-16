# Design: run-jobs-in-parallel

## D1. A process for each job

The host keeps a great deal of job state in its modules (the job, the lineup's values, the brief, the scratch of
searches), so two jobs cannot share a host process. The host becomes a DISPATCHER: it reads the queue and starts one
WORKER process for each job it takes (`python -m paperdaemon.pipeline.host --job <file>`), which works that one job
exactly as the host worked it before and ends. The dispatcher starts a job when:

- no other worker of this host has a job of the same notebook (the daemon also hands over one job per notebook), and
- the job is not LOCAL, or no local job runs in either library: a local worker holds the data folder's card lock
  (`paths.one_job`, shared by the Mirror's host and the False Mirror's) for its whole job; the dispatcher starts a
  local job only when it can take that lock, and hands the lock to the worker.

Pausing or restarting the host ends its workers with it (they are its children, ended by process tree and id).

## D2. Local is decided by the lineup

A job is local when its page's lineup has its TEXT model served at this computer's address, by its location (a
loopback host) or by a start script: a job spends its time in its text model's calls. A command-line text slot is
never local (the maintainer: command lines run in parallel). An image model on the card does not make a job local:
a picture is one call, and the engine gives the card to one picture at a time (card.py: a start script waits for the
calls in flight, pictures on a server of this computer one by one), so a cloud job's picture step waits its turn
without holding the job; a local job whose server was swapped out for it starts it again at its next call. A
lineup with a command line for text and a local model for pictures runs in parallel. A search server on this computer
does not make a job local.

## D3. The lineup of each request

Every request a worker makes to the engine (`/host/llm`, `/host/generate`, `/host/edit`, `/host/load`,
`/host/status`, `/host/search`, `/host/memories`) carries the job's lineup in the header `X-PD-Lineup`. The engine
sets it for that request alone (a context variable set by an ASGI middleware, read first by `settings.active`), so
every slot, harness and capability that request reads is that lineup's. `settings.use` (the lineup last named) stays
for what has no request: the window's status. The model a worker wants next (`/host/load`) is kept per lineup.

## D4. Files of each job

What a job wrote under a fixed name (the page read, the picture looked at, progress) is the job's own: temporary
pictures carry the worker's process id; progress is `run/progress/<doc>.json`. The host log takes every worker's lines,
each starting with its notebook's short id while more than one job runs.

## D5. Several jobs in flight in the daemon

`INFLIGHT` becomes one record per notebook. Each cycle the daemon checks each job in flight (recorded, the host
restarted, the page changed under it) and writes each one's progress note; it hands over the next page of every
notebook with nothing in flight. A conflict job is handed over only when nothing is in flight. `rm-inhand` is
written while any job is in flight and cleared when none is.

## D6. A job's push holds back the others' work

A worker records the documents it makes (`paths.note_made`, called where a new document's `.metadata` is first
written, when the process works a job: `run/jobs/<job>.made`). When a job is recorded the daemon pushes what is owed
except the notebooks of the other jobs in flight and the documents they made (`sync.push_pending(hold=...)`); those go
up when their own job is recorded. Abandon puts back what the job wrote to its notebook since it started and removes
the documents IT made (not every document made since).

## D7. Abandon ends one worker

`/queue/abandon` ends the worker of that job (by its process id, written in `run/jobs/<job>.pid`), not the host: the
other jobs run on. The page is settled as before.

## D8. The window

`/progress` answers every job being worked (a list); the library screens draw a bar on each of their covers. The job
list shows every job working at the top, in the order they started.
