# Tasks

## 1. Interface and rendering

- [x] 1.1 Define the reader interface (page in; lines, words and page-coordinate boxes out) in `paperdaemon/reader/` and verify with a unit test using a fake engine
- [x] 1.2 Render ink for reading (black on white, fixed scale, normalized widths) and map boxes back to page coordinates; verify a known stroke's box round-trips within one pixel

## 2. Windows OCR engine

- [x] 2.1 Call `Windows.Media.Ocr` in process through the WinRT projection and verify it reads a rendered test page on Windows
- [x] 2.2 Report the engine as unavailable on other systems and verify the host's fallback path records that handwriting was not read Done: `tests/test_reader.py` (elsewhere the reader is unavailable with its reason, and reading raises LookupError for the host to record).

## 3. The bar

- [x] 3.1 Assemble the first handwriting test set in `tests/handwriting/` from pages written for the project, with their true text, and document how to add pages Done differently, with the maintainer's word on real handwriting: twelve pages of GNHK (CC BY 4.0) from writers on four continents, in `paperdaemon/content/handwriting` with their words and its README.
- [x] 3.2 Write the measurement: word error rate and time per page for any engine, run as one command, and record Windows OCR's numbers here Done as the report card's handwriting test (`benchmark/probes.handwriting`: the share of words read, and seconds a page). Measured: Windows OCR reads 9-10% of GNHK's words (it is built for print), so the lineup's text model reads handwriting; the model's figure needs the real run.

## 4. Real-run evidence

- [ ] 4.1 On the maintainer's machine, with permission, read a set of the maintainer's own handwritten pages with each engine and record word error rate and time per page here, without keeping any page content
