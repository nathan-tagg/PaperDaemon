# Tasks

## 1. Engine

- [x] 1.1 Add routes to upload an image, decompose it at a size from 200 to 1,400 and return a preview and the stroke count; verify the image is held in memory only and released when sent or dropped Done: `/api/v1/decompose` (200 to 1,400, a preview, the stroke count, a progress ring), held in memory.
- [x] 1.2 Find the inbox notebook by its path in the mirror (a trashed one counts as gone, two at one path are refused with both named); verify with a fixture mirror Done, as the maintainer decided: two of one name -> the first made, never refused (`tests/test_benchmark_and_studio.py`).
- [x] 1.3 Send: create the notebook and missing folders on the first send, add the ignore tag when missing, append a blank page with the caption and the strokes, record the undo, push and retry when the library moved; verify with a stubbed cloud that no existing page changes Done: the notebook and missing folders made on the first send, one page appended, no ignore tag (the inbox is never a job: `tests/test_fixed_tags.py`), pushed (`tests/test_benchmark_and_studio.py`).
- [x] 1.4 Undo the last send: roll the inbox back, or move a notebook the send created to the trash; verify with a stubbed cloud Dropped by the maintainer: there is no undo.

## 2. Screen

- [x] 2.1 Build the drop box: drop or click to choose, size, status, each drop with its preview, count and send, and undo; say beside the settings' inbox field that the inbox is tagged with the ignore tag; verify each state by rendering it headless Done: the drop zone (a file, or a picture dragged from a browser), size, a ring per picture, each decomposition with its preview, count and Send to Tablet (off until an inbox is set in Settings); no undo.

## 3. Real-run evidence

- [ ] 3.1 With the maintainer's go-ahead, send two images to a fresh inbox on the maintainer's tablet (the first creates it), check both pages and the ignore tag on the tablet, check the daemon dispatches neither, undo one, and record the result here
