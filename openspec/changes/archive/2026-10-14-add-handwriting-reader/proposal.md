# Proposal

## Why

Most requests on a reMarkable are handwritten. The host has to know what the user wrote even when the
text model cannot see images, and it needs the words' positions to erase a request, mark up a word or
place an answer below it. The pipeline read handwriting with Windows OCR through PowerShell: good enough to
run on, Windows-only, and slow to start. PaperDaemon needs a reader of its own that is at least as good,
fast, and replaceable.

## What Changes

- A handwriting reader that turns a page's ink into lines of words with their positions on the page.
- One interface, several engines. On Windows the first engine is Windows OCR, called directly rather
  than through PowerShell; other engines can be added and picked in settings.
- A handwriting test set, and a measure of accuracy and speed that every engine is held to: at least as
  accurate as Windows OCR and at least as fast on the same pages.
- A clear fallback when no engine is available: the host still works from typed text and, when the
  text model can see, from the page image, and the job says handwriting was not read.

## Capabilities

### New Capabilities
- `reader/handwriting`: reading ink into words with positions, the engine interface and choice, the
  accuracy and speed bar, and the fallback.

### Modified Capabilities
None.

## Non-goals

- Cloud handwriting services.
- Reading typed text, which the host takes exactly from the page file.
- Recognizing drawings, shapes or diagrams.

## Impact

- New package `paperdaemon/reader/` with the engine interface and a Windows OCR engine.
- A dependency for calling Windows' OCR from Python (the WinRT projection packages) on Windows.
- A handwriting test set under `tests/handwriting/`, made from pages written for the project.
- A reader choice in the settings.
