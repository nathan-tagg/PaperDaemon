# Design

## Context

See proposal.md for why. In the pipeline, a tool is a function plus a JSON schema plus lines in the brief plus
a branch in the step runner (`rm_steps.KINDS`). Adding one touches four places in the host. This change
makes a tool one module.

## Goals / Non-Goals

**Goals:**
- Adding a tool touches one file.
- The brief's tool section is generated from the tools on offer.

**Non-Goals:**
- Sandboxing third-party tool code. A tool runs with PaperDaemon's permissions, like any Python module.

## Decisions

**A tool is a Python module with a small declaration and one action.** The declaration holds the name,
the model-facing description, a JSON schema with only required keys in declared order (llama.cpp's tool
grammar drops or respells a nested key written out of order), the needed capabilities, and whether it
acts outside the tablet. The action receives the step and a job context with the layout box, the page
and the slots.

**Kinds of step stay: host steps and drawing steps.** A host step (tag, wipe, fetch) runs without a page
box; a drawing step fills a box the layout solver gave it. The declaration says which.

**Outside-world tools reuse the explicit-direction check.** The same check the tag step uses (the
action's name appears in the notebook prompt, the typed text or the read handwriting) gates them, and
the capabilities screen shows them apart from tablet tools.

**Built-in tools first.** The drawing and search tools move behind the interface in this change; added
tools from the user's data folder are a later question.

## Risks / Trade-offs

- [A tool from outside the project runs arbitrary code] → Only tools in the codebase are loaded in this
  change; see Open Questions.
- [An outside-world tool fires on a loose match] → The direction check needs the action named, and the
  tool is off by default.

## Open Questions

Can wait:
- Loading tools from the user's data folder, and how to show the user what such a tool can do before
  it is switched on.
- Whether an outside-world tool should also ask for confirmation on the desktop before it runs.
