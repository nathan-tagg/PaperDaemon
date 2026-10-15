# Design

## Context

See proposal.md for why. The pipeline grew several benchmark suites (`bench_suite`, `bench_compose`,
`bench_rails`) that drove the host directly, and then a rule from the maintainer: only real dogfood jobs on
the tablet may back a claim. PaperDaemon's benchmark sits between the two. Like dogfood, it runs everything
real jobs run, from the daemon noticing a page to the commit, with the user's models. Like a bench, it
runs on pages that are not the user's, the same ones every time.

## Goals / Non-Goals

**Goals:**
- A user learns in one run what their configuration can do in PaperDaemon, and where its time goes.
- Two runs on two configurations can be read side by side.
- A developer uses the same benchmark before and after a change, as a regression check.

**Non-Goals:**
- Replacing dogfood on real pages. A pass says the pipeline works on these pages.

## Decisions

**The benchmark library is a real mirror.** Benchmark pages are real `.rm` files (typed text,
handwriting written for the project, pictures), laid out in the mirror's own format, so no part of the
pipeline can tell them from a real library. A run copies the library to a scratch folder and deletes
it after.

**The benchmark plays the tablet.** A case is a short script of page states: a page as it first
arrives, a tag added, a page written on again. The benchmark writes each state into the scratch mirror
the way the sync client writes a pull, then waits for the daemon. So the daemon's own change detection,
its ledger, retag handling and the ignore tag are exercised, not skipped. Pushes go to a local stand-in
that records them in the scratch mirror, so the commit path runs too and nothing leaves the machine.

**Its own daemon, and the user's jobs wait.** The benchmark starts a daemon on the scratch mirror with
its own ledger and no account. The user's daemon keeps watching the tablet but holds new jobs until
the run ends or is stopped, then dispatches them in order. A run asked for during a job begins when
that job ends. The two never share a model server, and hot swapping sees one job at a time.

**Consistent by construction.** A benchmark version fixes the cases, their order, and every picture's
seed. The models' sampling is whatever the harnesses set, as for real jobs. The report names the
benchmark version; changing a case changes the version, so two reports on one version measured the
same thing.

**Checks read the job record and the page.** Dispatch, placement, overlap, erasures and chart order
come from the daemon's and the host's own records and a re-read of the resulting page, never from the
model's claims.

**Times come from the records.** The host already records each job's phases, steps and durations
(spec: jobs/host), and hot swap records each start and stop. The report is built from those records,
so it times what real jobs do, with no second timer to disagree with them. Model speed is taken from
the server's own timings where it reports them.

**The model tests run first.** Each slot's "Test this model" check (spec: models/slots) runs before
the cases, so a capability mismatch, such as vision on for a model that cannot see, is reported before
the cases that depend on it.

**Handwritten cases use real ink.** Handwriting for the cases is written on a tablet for the project
and stored as strokes; synthetic handwriting would test a reader nobody uses.

## Risks / Trade-offs

- [A pass is read as proof for the user's own pages] → The report says what it measured and suggests a
  real page to try.
- [Cases overfit to the brief] → Cases test mechanisms with varied phrasing, and new cases come from
  real failures, rewritten as general rules.
- [A run holds the card, and the user's jobs, for a long time on slow models] → The report fills in as
  cases finish, and the user can stop the run at any point.
- [Models sample, so two runs on one configuration can differ] → Seeds fix the pictures; the report is
  one run, and says so.

## Open Questions

Can wait:
- How many cases the first benchmark needs, and who writes the handwritten ones.
- Whether to offer a short run and a full run.
- Whether to keep earlier runs' summaries (the configuration and the numbers, no pages), to compare
  configurations side by side.
- Whether to run each case more than once, to show how steady a configuration is.
