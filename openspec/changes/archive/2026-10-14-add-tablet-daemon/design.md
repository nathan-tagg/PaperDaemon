# Design

## Context

See proposal.md for why. The pipeline's daemon (`rm_daemon`) and scanner (`rm_scan`) run as separate
processes supervised by the studio. The scanner's rules came from real incidents: a fingerprint over
file bytes reopened pages the app merely re-saved, so the fingerprint became content-based; a change to
the fingerprint function once reopened fourteen finished pages at once; a tag that syncs before its ink
left pages stuck until "waiting" became a state; tagging a whole notebook would have dispatched every old
page until "baseline" existed.

## Goals / Non-Goals

**Goals:**
- Port those rules exactly; they are the behavior users of the pipeline already rely on.
- Run inside the engine, so the daemon, the API and the host share one process and one ledger.

**Non-Goals:**
- Parallel jobs. One graphics card, one job.

## Decisions

**Content fingerprints, not file hashes.** The fingerprint digests the page's strokes, typed text and
picture blocks in a canonical form. The reMarkable app rewrites files without changing what is on the
page; a byte hash would reopen those pages. The fingerprint function is versioned, and a test pins its
value on fixture pages, so an update that changes it fails the test suite (spec: an update never
reopens the library).

**Retagging is read from tag timestamps.** The reMarkable app stamps every tag when it is added. The
ledger keeps the stamp of the tag it last handled; a newer stamp on unchanged content means the user
removed and re-added the tag.

**Baseline is read from the same stamps.** A page is baseline when its last change is older than the
inherited tag's stamp at the moment the daemon first sees the tag.

**Settling is a quiet period after the last change.** The daemon waits until a page's fingerprint has
stayed the same across a short quiet period before dispatching. This is about the tablet's sync, not
the model, so a timer is appropriate here (the no-clock rule is about model output).

**The daemon is a thread in the engine with a lock file.** The data folder holds a lock taken at start;
a second process on the same folder finds it held and runs without a daemon. *Alternative:* a separate
daemon process, as in the pipeline. Rejected: two processes need a protocol, and the pipeline needed a supervisor to
restart its halves.

**Notification events from PaperDaemon's own device are ignored.** The sync client tags each event with the
device that caused it; the daemon pulls only for other devices' changes, and PaperDaemon's own pushes are
already in the mirror.

## Risks / Trade-offs

- [A fingerprint change reopens every finished page] → The pinned-value test, and the scanner reports
  "0 actionable" on an unchanged library before a new version dispatches anything.
- [The user expects a tagged notebook's old pages to be answered] → The overview shows baseline pages as
  such; editing a page brings it in.
- [Notifications silently stop] → The connection is marked stale after a long silence and reconnects;
  while it is down, the daemon checks the root at a low rate.

## Open Questions

Can wait:
- Whether several ready pages of one notebook go to the host as one job or one job each.
- The length of the settling period.
- What the daemon does with a ready page while the text model is not answering: hold it and retry, or
  record the failure and wait for the user.
- A back-and-forth mode that keeps watching one page for a while after answering it.
