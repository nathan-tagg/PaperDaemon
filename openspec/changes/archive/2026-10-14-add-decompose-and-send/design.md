# Design

## Context

See proposal.md for why. The pipeline's drop box has two parts: `decompose()`
fits the image into a square box of the chosen size (200 to 1,400 pixels, 1,200 by default) centered
in the page's safe area below a caption, and `send()` appends a page to one inbox notebook, making it
on the first send with the ignore tag on it. PaperDaemon ports both with the notebook taken from the
settings.

## Goals / Non-Goals

**Goals:**
- Parity with the pipeline's drop box.
- The preview is exactly what the tablet will show: it renders the strokes that will be sent.

**Non-Goals:**
- Anything the pipeline's drop box does not do (see the proposal's non-goals).

## Decisions

**Decompose on the engine, preview in the UI.** The UI uploads the image to the engine, which holds it
in memory under a random handle, decomposes it at the chosen size, and returns the stroke count and a
preview from the renderer (add-drawing-tools), cropped to the ink at half size, as in the pipeline. A
decomposed image stays listed with its preview until it is sent or the user leaves the screen, so
several can be dropped and sent one by one.

**The inbox is found by path, not by id.** `tablet.inbox` is a path like `Projects/Coloring inbox`: the
last part is the notebook's name, the rest its folders. The engine looks it up in the mirror each send.
A notebook in the trash counts as gone. Where two notebooks (or folders) on the path share a name, the one made
first is used, and the send is never refused (the maintainer's decision).

**A send is one push.** It waits for any cloud write in progress, pulls, then:

1. It makes the notebook and any missing folders when there is none.
2. It adds no tag: the daemon never answers the inbox, whatever it carries.
3. It appends a blank page with the caption and the strokes.
4. It pushes through the sync client (which records the library's state first, as every write does).

A push refused because the tablet moved the library mid-push is retried, as the pipeline retries four
times. Page files are addressed by their position among live pages, and index entries whose page file
never arrived are reconciled first. The pipeline learned both from real failures.

**The caption is the pipeline's, less the generation lines.** Above the drawing and aligned with it, in the
fineliner: the image's file name, then the seconds the decomposing took and the date and time. The
lines the pipeline adds for a generated picture (model, adapters, seed, steps) do not apply to a dropped
image.

**There is no undo** (the maintainer's decision); a page sent by mistake is deleted on the tablet.

## Risks / Trade-offs

- [A very detailed image makes a page with too many strokes for the tablet to draw quickly] → The
  stroke count is shown before sending, and a smaller size lowers it.
- [The user names one of their own notebooks as the inbox] → Sending adds the ignore tag to it, and jobs
  stop answering its pages. The settings screen says so beside the inbox field.

## Open Questions

None.
