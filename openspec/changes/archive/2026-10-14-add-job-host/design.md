# Design

## Context

See proposal.md for why. The pipeline's host (`rm_host.py`, about 7,200 lines) is one file holding the
brief, the tools, the page description, the plan and layout solver (`rm_plan`), the step runner
(`rm_steps`), the sweep, the notepad, the notebook prompt, commit and verification. It was tuned on the
maintainer's real pages against Qwen 3.6 27B. PaperDaemon keeps the behavior and splits the file by
responsibility, so that a model other than Qwen can run it and a reader can find things.

## Goals / Non-Goals

**Goals:**
- Behavior parity with the pipeline on the maintainer's pages, with the maintainer's models.
- A brief that is one base text plus small harness additions, not a fork per model.
- Every rule that matches words listed where an audit can find it.

**Non-Goals:**
- New job types beyond the pipeline's. They come through add-tool-extensions.
- Making the brief shorter or smarter while porting. Parity first; tuning later, on real runs.

## Decisions

**The host reads the page, then follows the harness's protocols** (the maintainer's decisions, 2026-09-26
and 2026-09-27; spec: models/harnesses).

1. The host receives the job and reads the page: typed text, the handwriting reader's lines, pictures
   and marks, and an image of it from the renderer (add-drawing-tools). It gathers the notebook's
   prompt, its notepad, the date and the location.
2. It hands those readings to the text slot's harness. The harness's `intake(job)` builds what the
   model is shown and told.
3. The host runs the turn through the slot's adapter and stops a runaway. The harness's
   `output(reply, job)` says what came back: tasks, a finished page, another turn, or a skip.
4. For each task, the harness's task protocol says what the host does: place and draw, run and return
   the result to the model, or nothing beyond checking.
5. The harness's `validate(result, job)` passes or refuses the result. The host commits what passes,
   updates the mirror and reports to the daemon.

The loop is the host's; every decision in it about the model is the harness's.

The Qwen 3.6 27B harness keeps the pipeline's reworked flow:
- Its first model turn is a forced call to the plan tool. The call carries the tasks, the places with
  a kind and rough size, the sources to fetch, and the erasures, named by the paragraph and mark
  numbers the host showed.
- Its task protocols leave every task's mechanics and placement to the host.
- The host returns to the model only for work that needs words after a lookup, such as writing an
  answer from search results.

That flow cut the benchmark from 621 s to 177 s. It is that harness's way of working, and the base
harness's (with the tool call asked for rather than forced), not a law of the host.

**The layout solver is pure.** `plan` lays places out in sequence inside the page's safe area, so they
cannot overlap; `near` a mark centers a place on it and clamps it into the safe area. It refuses with
numbers: no room, an unknown size, two places at one mark. Pure code with no job state means it is unit
tested with randomized layouts.

**Tasks by capability, the brief by the harness's intake.** The host decides which tasks can be on
offer from the slots: no image slot removes the picture and coloring tasks, and vision off means the
intake gets no image to show. Within that, the harness's task protocols choose. The base harness's
intake composes `base brief + harness additions + descriptions of the tasks on offer + the notebook's
prompt`, in that order, with the notebook's prompt last and word for word. The static part (base brief
and task descriptions) is kept byte-identical across jobs, so servers that cache a prompt prefix can
reuse it.

**The page as text for a model that cannot see.** Typed paragraphs verbatim with their numbers,
the reader's handwriting lines with positions as numbered marks, pictures and charts as labeled boxes.
The host never asks such a model to judge composition; the solver places everything.

**The notebook prompt is read from the page tagged `sprompt`.** Typed text first, handwriting through
the reader, cut at 10,000 characters. It goes at the end of the system message, where a Qwen chat
template renders it after the tool block, which is where it outranks the brief.

**The notepad is a Markdown file per notebook.** Entries carry a timestamp and the page's identity.
The model sees the most recent part (the pipeline shows about 2,600 characters) plus this page's own older
entries, relabeled with current page numbers. `/wipe` deletes the file.

**The notepad screen reads the same files the host does** (mockup: `docs/design/mockups/notepads.html`).
Three routes serve it:
- `GET /api/v1/notepads` lists the notebooks with a notepad, their entry counts and last entries,
  leaving the trash out.
- `GET /api/v1/notepads/{doc}` returns one notepad's entries, parsed and labeled with current page
  numbers, with skips marked. It also returns the text the next job would be shown, made by the same
  function the host calls, so the screen can never disagree with what the model gets.
- `DELETE /api/v1/notepads/{doc}` is the wipe.

The screen is a notebook list beside the chosen notepad. It has two views: the entries, with a line
where the model's window ends, and the exact text the next job is shown. New entries arrive the way
the overview's job rows do.

**The sweep's word lists are explicit and listed.** The carried-out test needs a work verb first
(questions never qualify) and a match between the line and what a step did: the kind of work named
(chart, picture, calendar) and a shared non-cue word, or, for a written answer, a words verb and a match
with what the answer says it answered. A redo verb (rewrite, redo, redraw, shorten, try again) lets a
job replace its own earlier work. The verb and noun sets and the 0.5 overlap were hand-picked on real
pages; they are listed in `paperdaemon/host/sweep.py` and in the job record when they fire, so the maintainer can
audit them for overfitting.

**Snapshots per document.** The host takes the sync client's per-document snapshot before its first
write; rollback swaps back that one document (tablet/sync).

## Risks / Trade-offs

- [The brief was tuned on Qwen 3.6 27B; other models may read it differently] → The base harness keeps
  the brief as is; a harness adds lines only when real runs show a need.
- [Word-matching rules overfit the maintainer's phrasing] → They are listed, logged when they fire, and
  checked on held-out pages.
- [A model that cannot force tool calls answers in prose] → The host asks again once with the tool named;
  a second prose reply is recorded as a failed job.
- [Porting a 7,200-line file introduces regressions] → Port by responsibility with the maintainer's real
  pages as the held-out check, and keep the pipeline running unchanged beside it.
- [Ink the user adds to a page while its job runs is overwritten when the job commits] → Accepted, as
  in the pipeline (the maintainer, 2026-09-27). Nothing adjusts for it.
- [A harness's validate() trusts its model too far] → Trust is the harness's to set, by design; the
  base validate() is the careful default, and a user harness is the user's own code.

## Open Questions

Can wait:
- Whether the notepad's shown length should scale with the model's context size.
- A keep-watching mode after an answer, for back-and-forth on one page.
