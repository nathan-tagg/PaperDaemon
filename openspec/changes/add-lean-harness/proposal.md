# Proposal: add-lean-harness

## Why

A model reached through a command line or a hosted API is dear to call, and a strong one needs little telling. The
default harness was shaped for a local model: a long job description, every tool sent on every turn so that the
server's cached prefix holds, and one turn for the plan and one more for every step. On the maintainer's Opus lineup
that was three or four calls a job, each carrying about ten thousand tokens of instructions and tools before the
page. His ruling (11-10): "we really need to trim down the tooling for the advanced models ... they get their
kitting advertised to them, the job description, the renders / .rm data that they need, and are told to save tokens
intrinsically within the intake / steps", "competent models in general need far less tasks per job", "a 'Lean
Default (stronger models only)' version and then harnesses for opus, sonnet, and haiku".

## What Changes

- A text harness field, `lean`. A lineup whose harness is lean is worked the lean way:
  - a short job description that keeps every rule the host enforces and advertises each kind of step in a line;
  - a turn is sent only the calls it may make (the decision's four and the looks; a step's own), with an id a plain
    string the host checks, as it always has;
  - a page that holds typed text and nothing else is sent as its listing, with no picture;
  - a plan's step may carry its content (a write's lines, a sketch's parts, a chart's spec), which is made from
    with no turn of its own, so a job of words and a sketch is one call. A write whose plan has a search is still
    asked for with the results. A chart or a calendar is asked for when its step runs, with the types and facts it
    needs. A sketch is still shown back once.
- Shipped harnesses: "Lean Default (stronger models only)", and on it "Claude Opus 5.5", "Claude Sonnet 5.5" and
  "Claude Haiku 5.5", picked by the model's name.
- The default harness and every lineup on it are unchanged.

## Impact

- Affected specs: models/harnesses (the `lean` field and the shipped lean harnesses), jobs/host (content given with
  the plan)
- Code: `paperdaemon/harnesses/` (the field, the shipped files, the guide), `paperdaemon/loop.py` (the host is
  told), `paperdaemon/pipeline/host/__init__.py` (the lean brief; content from the plan), `decision.py` (a turn's
  own calls), `model.py`, `steps.py` (the short step list; lines and parts on a step), `intake.py` (a typed page)
- Tests: `tests/test_lean_harness.py`
