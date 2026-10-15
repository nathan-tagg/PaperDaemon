# Design

## Context

See proposal.md for why. The pipeline's reader (`rm_ocr`) renders the page's ink to an image and runs
`Windows.Media.Ocr` through a PowerShell process. It reads the maintainer's handwriting well enough to run
on, misses some of it intermittently (the `/wipe` command needed a model-side fallback for that
reason), costs a process start per page, and exists only on Windows. A survey of engines is in
`docs/research/handwriting-ocr.md`.

## Goals / Non-Goals

**Goals:**
- A reader behind one interface, so engines can be compared and swapped without touching the host.
- A number for "good enough": word error rate and time per page on a fixed test set, with Windows OCR
  as the bar.

**Non-Goals:**
- Training or fine-tuning a model.
- A cloud engine, even as an option. This change stays on this computer.

## Decisions

**The interface takes ink, not only an image.** `read(page) -> [Line(words=[Word(text, box)])]`, where
`page` carries the strokes and a way to render them. Image engines render; stroke engines use the pen's
path and order, which carries information a rendered image loses. This keeps stroke-based recognizers
(the Windows Ink recognizer, MyScript) open as engines. *Alternative:* an image-only interface, which is the
pipeline's shape. Rejected because it rules out the most promising class of engines before they are measured.

**Windows OCR first, called in process.** The WinRT projection for Python calls `Windows.Media.Ocr`
without a PowerShell process per page. It is the engine the bar is defined by, so it is the first
engine. *Alternative:* keep the PowerShell bridge. Rejected for the start-up cost and the parsing of
console output.

**Render for the reader, not for the eye.** Ink is rendered black on white at a fixed scale with pen
widths normalized, since the recognizer's accuracy depends on stroke weight more than on looks.
Positions map back to page coordinates through the same transform, so boxes land on the ink.

**The test set is written for the project.** Pages written by volunteers for the purpose, with their
true text beside them, kept in `tests/handwriting/`. Public handwriting datasets mostly forbid
redistribution. The maintainer's own pages stay private and serve as the held-out check, run on the maintainer's
machine only.

**Engines to measure next,** from `docs/research/handwriting-ocr.md`:

- **RapidOCR with PP-OCRv6** (Apache-2.0, ONNX Runtime on the CPU, about 100 MB of wheels): the portable
  engine for every platform and the only published handwriting numbers among light engines (61 to 68%
  of handwritten English lines exactly right; about 0.6 to 1.4 s per image on a server CPU). Its word
  boxes are derived from character positions, so they need checking against the ink.
- **Apple Vision through PyObjC** on macOS: built in, fast, a box per word, no documented handwriting
  support.
- **Windows' stroke recognizer (`InkAnalyzer`)**, unverified from Python: it returns each word's
  strokes, which would make erase targets exact instead of box-based.
- **A vision language model as a second reader** for lines the fast engine reads badly: it corrects the
  text while the fast engine keeps the boxes. It needs the graphics card or the chat model's own vision,
  so it is optional.

Each engine declares what it can do: platforms, download size, whether its word boxes are native,
derived or generated, and whether it gives confidences (Windows OCR does not). Each engine owns its
preprocessing (Windows OCR misses small writing unless the render is upscaled, and caps images at
10,000 px a side). The Snipping Tool's engine reads well but cannot be redistributed, and reMarkable's
own conversion has no API.

## Risks / Trade-offs

- [Windows OCR is tuned for print and misses some handwriting] → It is the bar, not the ceiling; the
  interface exists so a better engine can replace it.
- [There is no engine at all on Linux at first] → The host's fallback runs jobs from typed text and the
  page image; the job record says handwriting was not read.
- [A small test set flatters an engine] → Report the set's size with every result, and hold the maintainer's
  pages out as a second check.

## Open Questions

Decide before the engine is chosen for macOS and Linux:
- Which engines clear the bar, once `docs/research/handwriting-ocr.md` is reviewed and the candidates
  are measured.

Can wait:
- Who writes the test set pages, and how many are enough.
- Whether a stroke-based engine should also report its alternatives for each word.
