# Handwriting OCR for PaperDaemon

Desk research, checked 2026-09-26. Nothing was installed or benchmarked for this report. The only
local check was reading `OcrEngine.MaxImageDimension` (10,000 px) on Windows 11 build 26200.

**What PaperDaemon needs:** read handwriting (print or cursive, from adults and children) off a rendered page
(1620×2160 page units, usually rendered at 2× = 3240×4320 px, dark ink on white). It must return
lines and words with boxes, because the host erases or marks individual words. It has to run
offline on the CPU in seconds per page (the GPU is busy with the local LLM), ship light, and work
on Windows first, macOS and Linux if possible.

## Recommendation

1. **Windows: keep Windows OCR, but call it in-process through PyWinRT.** Replace the PowerShell
   bridge with `winrt-Windows.Media.Ocr`, five sibling namespace packages and `winrt-runtime` (MIT,
   roughly 1 MB of wheels, Python 3.9–3.14). It is the same engine with the same line and word
   rectangles. There is no model to download and no PowerShell process per page. Treat it as the
   zero-download baseline: Microsoft now calls this API "legacy", documents no handwriting support,
   and it returns no confidence scores.
2. **All platforms: add RapidOCR running PP-OCRv6 as the portable engine.** Code and models are
   Apache-2.0, and it runs on ONNX Runtime on the CPU. PP-OCRv6 (June 2026) is a small model family
   (1.5M–34.5M parameters) with published handwriting numbers. On Baidu's handwritten-English line
   set, the share of lines read exactly right is 67.8% (medium, 34.5M parameters) and 61.1%
   (small). PP-OCRv5 server scores 59.6% and Qwen3-VL-235B scores 73.2% on the same set. Baidu's CPU
   latency is 0.59 s (small) and 1.40 s (medium) per image (Xeon 8350C, OpenVINO). Lines come back
   as quadrilaterals. Word boxes are derived from character positions inside each line
   (`return_word_box=True`), so they are approximate. On Windows the install is roughly 100 MB of
   wheels: rapidocr 27 MB (includes the small models), onnxruntime 14 MB, opencv-python 44 MB, plus
   numpy and shapely. The medium models add about 130 MB (PaddleOCR's figures).
3. **macOS: use Apple Vision through PyObjC,** with RapidOCR as the alternative. It is built into
   the OS and takes about 0.13–0.21 s per image on an M3 Max (ocrmac's numbers). It returns line
   observations, and `boundingBox(for:)` gives a box for each word. Apple documents no handwriting
   support. Users report it reads neat handwriting well.
4. **Linux: use RapidOCR with PP-OCRv6.** Linux has no OS engine.
5. **Hard pages: offer a small vision-language model (VLM) as an optional second reader, not as the
   default.** VLMs read handwriting far better than light OCR. In OmniHandwritingOCR (August 2026),
   Qwen3-VL-8B has a 16.4% character error rate (CER) on English handwriting, against 43.2% for
   GOT-OCR2 and 47.5% for PaddleOCR-VL. But VLMs are slow on the CPU (estimated from token counts:
   minutes per page with word boxes), and their boxes are generated numbers. Run one on the GPU when it is
   free, or reuse the chat model if it is itself a VLM (Qwen3.5 and Qwen3.6 take images natively).
   Use it to correct the text of bad lines while the fast engine keeps the boxes.
6. **reMarkable's own conversion (MyScript) has no API.** The tablet sends strokes to reMarkable's
   cloud, which forwards them to MyScript under reMarkable's key. Community tools instead call
   MyScript directly with the user's own developer key. That is cloud-only, so it fails the offline
   requirement.

**Evidence gap:** no public benchmark scores Windows OCR on handwriting, so "equivalent or superior
to Windows OCR" can only be settled with real runs. Run Windows OCR and PP-OCRv6
(small and medium) on real tablet pages: print and cursive, adult and child. Compare word accuracy
and whether each word's box covers its ink. If PP-OCRv6 wins, make it the Windows default and keep
Windows OCR as the no-download fallback.

### Pluggable design

- **One interface:** `read(image, languages) -> Page`, where a page holds lines and each line holds
  words. Each line and word has text, a four-point box in source-image pixels (top-left origin),
  and a confidence or `None`. Each engine converts its native coordinates: Windows OCR returns
  pixel rectangles (valid as-is when `TextAngle` is 0), Vision returns normalized rectangles with a
  bottom-left origin, RapidOCR returns pixel quadrilaterals, and Qwen returns boxes on a 0–1000
  grid.
- **Each engine declares its capabilities:** platforms, offline or not, download size, word-box kind
  (native, derived, or generated), whether it gives confidences (Windows OCR does not), and the
  languages available right now. Windows OCR needs a language pack per language; Vision lists its
  languages at runtime.
- **Engines own their preprocessing.** Windows OCR misses small text unless the image is upscaled
  (the prototype upscales 2×) and caps images at 10,000 px per side. PP-OCR resizes internally.
  VLMs need downscaling, because Qwen3-VL spends one token per 32×32 px.
- **A registry picks the default for each platform, and settings can override it.** An engine that
  cannot run (no language pack, model not downloaded, wrong OS) reports why instead of returning an
  empty word list.
- **Keep boxes and text separable,** so a slow reader can correct the text while the fast engine
  keeps the boxes. The host only ever sees word boxes, whichever engine produced them.
- **Keep one set of real pages with hand-checked words.** The same set chooses defaults and catches
  changes in OS engines after OS updates; for example, a regression in mixed Chinese/English Vision
  OCR has been reported on a macOS 27.2 beta.

## Comparison

| Option | Handwriting evidence | Word boxes | CPU speed | Ship size | License | Platforms | Maintained |
|---|---|---|---|---|---|---|---|
| Windows.Media.Ocr via PyWinRT | None published; "legacy" per Microsoft | Native rectangles; lines; no confidence | ~48 ms/image in winocr's test (image size not stated) | ~1 MB wheels; engine in OS, language pack per language | MIT (PyWinRT); OS part | Windows 10/11 | PyWinRT 3.2.1 (Jun 2025); API unchanged since 2015 |
| Windows AI Text Recognition | "Common forms of handwritten text"; no numbers | Native quads + confidence | NPU only | OS model; MSIX-packaged app | OS part | Copilot+ PCs only | Active |
| Apple Vision via PyObjC | Not documented; users report it reads neat handwriting well | Per word via `boundingBox(for:)` | 0.13–0.21 s/image (M3 Max) | Small PyObjC wheels; engine in OS | MIT (PyObjC); OS part | macOS 10.15+ | Active (PyObjC 12.2.2, Aug 2026) |
| RapidOCR + PP-OCRv6 | 61.1% small / 67.8% medium exact lines, handwritten English (vendor) | Line quads; derived word boxes | 0.59 s small / 1.40 s medium per image (vendor) | ~100 MB wheels on Windows | Apache-2.0 | Win, macOS, Linux | Active (3.9.2, Jul 2026) |
| PaddleOCR 3.7 | Same models | `return_word_box` (axis-aligned) | Same models | Larger stack; several backends | Apache-2.0 | Win, macOS, Linux | Active (3.7.0, Jun 2026) |
| TrOCR (handwritten) | IAM line CER 3.42 (base), 2.89 (large) | None; line recognizer that needs a detector | Not published for CPU | 1.33 GB (base) + PyTorch 227 MB | MIT | Any | Frozen (2021 models) |
| docTR / OnnxTR | No handwriting model | Native word detection | 0.15–0.57 s/page (printed forms) | Small with OnnxTR | Apache-2.0 | Any | Active (Aug 2026) |
| EasyOCR | Handwriting still on its roadmap | Region boxes | Not published | PyTorch + models | Apache-2.0 | Any | Stale (Sep 2024) |
| Tesseract | FAQ: "won't work very well" | Native (TSV, hOCR) | ~0.8 s for a small printed invoice (CodeSOTA) | Native binary + data files | Apache-2.0 | Any | Active (5.5.3, Jul 2026) |
| Surya 2 | Demo only; no numbers | Blocks only | ~9 s/page on Apple silicon | 650M-param model + llama.cpp | Code Apache-2.0; weights restricted | Any | Active |
| Florence-2 | Anecdotal only | Region quads | "Very slow" on CPU | 0.23B / 0.77B + PyTorch | MIT | Any | 2024 model |
| GOT-OCR 2.0 | 43.2% CER, English handwriting | None | Not published | 0.6B + PyTorch | Apache-2.0 | Any | 2024 model |
| olmOCR-2 | Claims handwriting | None | GPU only (NVIDIA, 12 GB+) | 7B | Apache-2.0 | Linux + NVIDIA | Active |
| Qwen3-VL / Qwen3.5 (0.8–9B) | 8B: 16.4% CER, English handwriting; 2B/4B untested | Generated, 0–1000 grid | Minutes/page with word boxes (estimate) | 4-bit: <2 GB (2B), ~3 GB (4B) | Apache-2.0 | Any (llama.cpp) | Active |
| reMarkable conversion | MyScript, reads strokes | n/a | Cloud | n/a | Proprietary | Tablet, desktop app | No public API |

"Exact lines" is PP-OCR's strict metric: one wrong character, including punctuation, fails the
whole line. Word-level accuracy is higher than these numbers. CER is character error rate (lower is
better). No benchmark found covers children's handwriting. IAM and GNHK are English sets.

## Options

### Windows.Media.Ocr via PyWinRT

- **API:** `OcrEngine.RecognizeAsync(SoftwareBitmap)` returns `OcrResult.Lines`. Each line has
  `Words`, and each word has only `Text` and `BoundingRect` (pixels from the top-left, valid when
  `TextAngle` is 0). There is no confidence value. The maximum image size is 10,000 px per side
  (read locally), so a 3240×4320 render, even upscaled 2×, fits.
- **Languages:** 25 languages. Each needs its OCR pack, installed through Settings or with
  `Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"` (requires admin). List the
  installed ones with `OcrEngine.AvailableRecognizerLanguages`.
- **Handwriting:** Microsoft documents none. It describes its NPU-only replacement as "faster and
  more accurate than the legacy Windows.Media.Ocr.OcrEngine APIs". The prototype found it
  acceptable but not great on handwriting.
- **Speed:** the winocr project reports 1,000 images in 48 s in one process, but does not state the
  image size. No page-level number was found.
- **Packages:** PyWinRT's last release was 3.2.1 in June 2025, with Python 3.14 wheels added in
  September 2025. Release 3.2 added buffer-protocol arguments and a synchronous `.get()` on async
  operations. The call below follows those release notes and winocr's source. It was **not run**
  for this report:

```python
# pip install winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging \
#   winrt-Windows.Globalization winrt-Windows.Storage.Streams \
#   winrt-Windows.Foundation winrt-Windows.Foundation.Collections
from PIL import Image
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine

def read_words(path, lang="en-US"):
    img = Image.open(path).convert("RGBA")
    bmp = SoftwareBitmap.create_copy_from_buffer(          # bytes as IBuffer needs PyWinRT >= 3.2;
        img.tobytes(), BitmapPixelFormat.RGBA8,             # winocr uses DataWriter.detach_buffer()
        img.width, img.height)
    engine = OcrEngine.try_create_from_language(Language(lang))  # None if the language pack is missing
    result = engine.recognize_async(bmp).get()
    return [(w.text, w.bounding_rect.x, w.bounding_rect.y,
             w.bounding_rect.width, w.bounding_rect.height, i)
            for i, line in enumerate(result.lines) for w in line.words]
```

### Windows AI Text Recognition (Copilot+ PCs only)

This is Microsoft's successor, `Microsoft.Windows.AI.Imaging.TextRecognizer` in the Windows App
SDK. It returns lines and words with four-point boxes and a confidence per word, and Microsoft says
it handles "common forms of handwritten text". But Microsoft's hardware table lists it as NPU only,
with CPU and GPU both "not supported". It also needs an MSIX-packaged app declaring the
`systemAIModels` capability. It could be an optional engine for Copilot+ users, but not a baseline.

### Apple Vision via PyObjC

- **Calling it:** `pyobjc-framework-Vision` (MIT, 12.2.2, August 2026) exposes
  `VNRecognizeTextRequest`. ocrmac (MIT, 1.0.1, January 2026) is a small working wrapper.
- **Recognition paths:** the accurate path finds lines and then words, and it tokenizes on
  whitespace. That makes per-word boxes available through
  `topCandidates(1)[0].boundingBoxForRange_error_(NSRange(start, len), None)`. Boxes are normalized
  with a bottom-left origin, and ranges count UTF-16 code units.
- **Languages:** 18 per WWDC24, and more on macOS 26. Query them at runtime.
- **Handwriting:** Apple's documentation says nothing about it. A 2019 tutorial warned against
  "raw handwriting". In 2022 one user reported "99.9% correct" results on a cookbook printed in
  "immaculate" handwriting. No benchmark was found.
- **Newer APIs:** Apple's newer document APIs (`RecognizeDocumentsRequest`, macOS 26) are Swift-only
  ("Vision will only introduce new features in Swift moving forward"), so PyObjC is limited to the
  classic request.

```python
import Vision
from Foundation import NSURL
req = Vision.VNRecognizeTextRequest.alloc().init()
req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
req.setRecognitionLanguages_(["en-US"]); req.setUsesLanguageCorrection_(True)
h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
h.performRequests_error_([req], None)
lines = [(o.topCandidates_(1)[0].string(), o.boundingBox()) for o in req.results()]
```

### RapidOCR (PP-OCR on ONNX Runtime)

- **What it is:** Apache-2.0, with models redistributed under PaddleOCR's Apache-2.0 license. It
  runs on ONNX Runtime, OpenVINO, MNN, Paddle, TensorRT or PyTorch.
- **Releases:** 3.9.0 (June 23, 2026) made PP-OCRv6 small the default detector and recognizer; the
  wheel grew from 15 to 29 MB. 3.9.1 and 3.9.2 followed in July 2026.
- **Output:** `engine(img, return_word_box=True)` returns line quads (`boxes`, `txts`, `scores`)
  plus `word_results`: text, score and a quad for each word (for each character in Chinese text).
  Word boxes come from character positions in the recognizer output inside the line crop.
  DeepWiki, a third-party summary, puts the extra cost at 20–35% of OCR time.
- **Dependencies:** onnxruntime is installed separately (1.30.0, 14.3 MB for Windows x64). The
  package depends on opencv-python (44 MB for Windows).
- **Handwriting:** the same as PP-OCRv6 below.

### PaddleOCR 3.x (PP-OCRv5, PP-OCRv6)

- **Releases:** 3.7.0 (June 11, 2026) shipped PP-OCRv6 as the default: tiny, small and medium have
  1.5M, 7.7M and 34.5M parameters. Small and medium cover 50 languages (Chinese, English, Japanese
  and 46 Latin-script languages).
- **Handwritten-English exact-line accuracy** (PP-OCRv6 paper, Table 6): tiny 39.3%, small 61.1%,
  medium 67.8%, PP-OCRv5 server 59.6%, PP-OCRv5 mobile 50.9%, Qwen3-VL-235B 73.2%,
  Gemini-3.1-Pro 73.0%, GPT-5.5 56.9%.
- **CPU latency** (Table 9, Xeon 8350C, OpenVINO, full detection + recognition per image): tiny
  0.20 s, small 0.59 s, medium 1.40 s, PP-OCRv5 server 7.30 s. These are vendor numbers on the
  paper's photos and documents, not handwritten pages.
- **Model sizes:** detection 1.9, 9.6 and 59.4 MB; recognition 4.4, 20.4 and 73.3 MB.
- **Word boxes:** `return_word_box=True` computes them on the straightened line crop. On rotated
  lines they come back axis-aligned and inflated (PaddleOCR discussion #17150).
- **Backends:** besides Paddle, it can run on ONNX Runtime, OpenVINO or Transformers. RapidOCR is
  still the lighter way to ship the same models.

### TrOCR (handwritten)

- **Models:** MIT. Small, base and large have 62M, 334M and 558M parameters, with IAM line CER of
  4.22, 3.42 and 2.89 (paper, Table 4).
- **Limits:** it reads single text lines only and was fine-tuned on IAM, which is adult English. It
  needs a line detector and gives no word boxes.
- **Speed and size:** the paper reports 4.6 lines/s for base with beam search of 10, but not the
  hardware for that table. No CPU numbers were found. The base checkpoint is 1.33 GB, plus
  PyTorch (227 MB Windows wheel).
- **Verdict:** a fine-tuning base, not a drop-in engine.

### docTR / OnnxTR

- **Word boxes:** Apache-2.0. Its detection stage localizes words, so word boxes are native.
- **Handwriting:** no handwriting model exists. The request has been open since 2022 (issue #1049).
  A December 2025 answer in the project's discussions says CRNN recognizers "work best for
  handwritten text" and suggests fine-tuning on IAM or RIMES.
- **Speed:** OnnxTR (ONNX only, no PyTorch) reports 0.57 s per page at FP32, 0.38 s at 8-bit and
  0.15 s with OpenVINO, on an i7-14700K with the FUNSD printed-forms set.
- **Releases:** docTR 1.1.0 and OnnxTR 0.9.0 both came out in August 2026.
- **Possible hybrid (not verified):** its word detector feeding a handwriting recognizer.

### EasyOCR

Apache-2.0, PyTorch, CRAFT detection plus a CRNN recognizer. It returns a box, text and confidence
for each detected region. "Handwritten text support" is still listed under "What's coming next".
The last release was 1.7.2 in September 2024. Not recommended.

### Tesseract

Apache-2.0; 5.5.3 came out in July 2026. It gives native word boxes (TSV, hOCR). Its FAQ on
handwriting: "You can, but it won't work very well, as Tesseract is designed for printed text." It
ships as a native binary, not a pip wheel. Not recommended.

### Surya (Datalab)

Surya 2 is a 650M-parameter OCR model served through vLLM (NVIDIA) or llama.cpp (CPU and Apple
silicon). Its OCR returns layout blocks as HTML with polygons, not word boxes. It reports
0.108 pages/s on Apple silicon; no x86 CPU figure was published. The code is Apache-2.0, but the
weights use a modified OpenRAIL-M license that is free only "for research, personal use, and
startups under $5M funding/revenue". A permissive app would pass that restriction on to its users.
There is a handwritten-notes demo but no numbers. Datalab's Chandra (4–9B, same weights license)
targets handwriting but is heavier still.

### Florence-2

MIT; 0.23B and 0.77B parameters. It is native in Transformers
(`Florence2ForConditionalGeneration`). `<OCR_WITH_REGION>` returns quads and labels; the grouping
into words or lines is not documented. Roboflow says it reads handwriting "with significant
accuracy", but gives no benchmark. They time it at about 1 s per image on a T4 GPU and warn that
CPU inference "may be very slow". No handwriting benchmark was found.

### GOT-OCR 2.0

Apache-2.0, 0.6B parameters, native in Transformers. It outputs text or formatted text only, with no
boxes, though it can read a region you give it. On OmniHandwritingOCR's English handwriting (IAM
lines + GNHK) its CER is 43.2%, against 16.4% for Qwen3-VL-8B. Weak on handwriting.

### olmOCR (Allen AI)

olmOCR-2 (October 2025) is a 7B Qwen2.5-VL fine-tune, Apache-2.0 for code and weights. Its README
lists handwriting among supported content. It outputs Markdown with no boxes and needs an NVIDIA
GPU with at least 12 GB. Not a fit.

### Qwen VL models (Qwen3-VL, Qwen3.5)

- **Models:** Qwen3-VL (October 2025) comes in 2B, 4B, 8B and 32B dense sizes and MoE versions,
  Apache-2.0. Its README says it reads 32 languages (the technical report says 39), and its
  grounding uses coordinates "normalized ... to the range [0,1000]". Qwen3.5 small (March 2026)
  comes in 0.8B, 2B, 4B and 9B, Apache-2.0, all taking images natively. At 4-bit they need under
  2 GB (2B) and about 3 GB (4B). Qwen3.6-27B (April 2026) is
  also image-text-to-text under Apache-2.0.
- **Handwriting:** in OmniHandwritingOCR, Qwen3-VL-8B scores 16.4% CER on English handwriting, on
  par with Qwen2.5-VL-72B (16.0%), which is the lowest of 13 models. The 2B and 4B were not tested.
  Crosilla et al. (2025) likewise find VLMs strong on modern English handwriting and weaker in
  other languages.
- **Word boxes:** they are generated as text. One reported issue: every line's words start at the
  same x (Qwen3-VL issue #1231).
- **CPU cost (estimate, not measured):** Qwen3-VL uses 16-px patches merged 2×2, which is one image
  token per 32×32 px. A 1620×2160 page is about 3,400 image tokens; a 3240×4320 render is about
  13,700, so downscale first. A word-level answer with boxes runs about 15–25 tokens per word, which
  is thousands of tokens per page. At the assumed CPU decoding speed of a 2–4B model (tens of tokens
  per second), that means minutes per page.
- **Licenses to avoid:** Qwen2.5-VL-3B uses the "qwen-research" license. Nanonets-OCR2-3B (19.4%
  CER), a fine-tune of it, states no license. GutenOCR (January 2026) trains Qwen2.5-VL-3B and 7B
  to output line boxes.

### reMarkable's conversion (MyScript)

- **How it works:** the tablet sends pen strokes to a reMarkable cloud server, which forwards them
  to MyScript under a key reMarkable keeps off the device. Conversion needs Wi-Fi and a reMarkable
  account; converting from the desktop app needs Connect. No public or documented endpoint was
  found, and no reverse-engineered one either.
- **Community tools:** rescript, rmapi-hwr and remarkable-myscript-mcp call MyScript's cloud REST
  API directly with the user's own developer keys. A MyScript staff forum post from about 2021 gives
  2,000 free requests a month, paid beyond that. MyScript's JIIX output has word
  bounding boxes in millimeters; they cover the ink when `conversionState` is left out.
- **Verdict:** cloud-only and bring-your-own-key. At most an opt-in engine.

### Also looked at

- **OneOCR** (the Snipping Tool's engine) can be driven from Python (oneocr, owocr); owocr calls it
  "one of the best local engines to date". It needs Microsoft's `oneocr.dll` and model copied out
  of the Snipping Tool package. Those are proprietary files from a Microsoft Store app, and nothing
  grants a right to redistribute them, so a published app cannot bundle them.
- **Document parsers tested in OmniHandwritingOCR** (English handwriting CER): MonkeyOCR-pro-1.2B
  23.6%, DeepSeek-OCR 39.8% (MIT, 3.3B), PaddleOCR-VL 47.5% (Apache-2.0, 0.9B), MinerU2.5 93.4%.
  None beats Qwen3-VL-8B, and all are far heavier than PP-OCR.

### Outside the brief (proposal only)

PaperDaemon already has the strokes it renders: Windows' built-in stroke recognizer (`InkAnalyzer`,
PyWinRT package `winrt-Windows.UI.Input.Inking.Analysis`) returns each word's text, rectangle and
stroke IDs, which are exact erase targets; macOS 27's `PKStrokeRecognizer` is the Swift-only
equivalent. Neither was verified from Python, and no accuracy numbers were found.

## Sources

All checked 2026-09-26.

Windows
- https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine?view=winrt-26100
- https://learn.microsoft.com/en-gb/uwp/api/windows.media.ocr.ocrengine.maximagedimension?view=winrt-26100
- https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrword?view=winrt-26100
- https://blogs.windows.com/windowsdeveloper/2016/02/08/optical-character-recognition-ocr-for-windows-10/
- https://pypi.org/project/winrt-Windows.Media.Ocr/
- https://pypi.org/project/winrt-runtime/
- https://pypi.org/project/winrt-Windows.Graphics.Imaging/
- https://github.com/pywinrt/pywinrt/releases/tag/v3.2.0
- https://github.com/GitHub30/winocr (README.md, winocr.py, setup.py)
- https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition
- https://learn.microsoft.com/en-us/windows/ai/apis/
- https://learn.microsoft.com/en-us/windows/ai/apis/get-started
- https://learn.microsoft.com/en-us/windows/ai/cards/text-recognition-ocr-platform-card
- https://learn.microsoft.com/en-us/windows/uwp/ui-input/convert-ink-to-text
- https://learn.microsoft.com/en-us/uwp/api/windows.ui.input.inking.analysis.inkanalyzer?view=winrt-26100
- https://pypi.org/project/winrt-Windows.UI.Input.Inking.Analysis/
- https://github.com/AuroraWright/owocr
- https://github.com/AuroraWright/oneocr
- https://b1tg.github.io/post/win11-oneocr/

Apple
- https://developer.apple.com/documentation/vision/vnrecognizetextrequest
- https://developer.apple.com/documentation/vision/recognizing-text-in-images
- https://developer.apple.com/videos/play/wwdc2024/10163/
- https://developer.apple.com/videos/play/wwdc2025/272/
- https://developer.apple.com/videos/play/wwdc2026/203/
- https://pypi.org/project/pyobjc-framework-Vision/
- https://github.com/straussmaximilian/ocrmac and https://pypi.org/project/ocrmac/
- https://yasoob.me/posts/how-to-use-vision-framework-via-pyobjc/
- https://www.hackingwithswift.com/example-code/vision/how-to-use-vnrecognizetextrequests-optical-character-recognition-to-detect-text-in-an-image
- https://discourse.devontechnologies.com/t/apple-live-text-vision-framework-ocr/69414
- https://github.com/mkyt/ocrmypdf-AppleOCR
- https://github.com/missuo/macos27-vision-ocr-bug

PaddleOCR and RapidOCR
- https://github.com/RapidAI/RapidOCR and https://github.com/RapidAI/RapidOCR/releases
- https://pypi.org/project/rapidocr/
- https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
- https://deepwiki.com/RapidAI/RapidOCR/6.3-word-level-information (third-party summary)
- https://github.com/PaddlePaddle/PaddleOCR and https://github.com/PaddlePaddle/PaddleOCR/releases
- https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html
- https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html
- https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec
- https://arxiv.org/html/2606.13108v1 (PP-OCRv6 paper)
- https://huggingface.co/blog/PaddlePaddle/pp-ocrv6
- https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_safetensors
- https://github.com/PaddlePaddle/PaddleOCR/discussions/17150
- https://pypi.org/project/onnxruntime/ (1.30.0 files)
- https://pypi.org/project/opencv-python/ (5.0.0.93 files)

Other engines
- https://arxiv.org/abs/2109.10282 (TrOCR paper, Tables 4 and 5)
- https://huggingface.co/microsoft/trocr-base-handwritten
- https://pypi.org/project/torch/ (2.14.0 files)
- https://github.com/mindee/doctr, https://pypi.org/project/python-doctr/
- https://github.com/mindee/doctr/issues/1049, https://github.com/mindee/doctr/discussions/2034
- https://github.com/felixdittrich92/OnnxTR, https://pypi.org/project/onnxtr/
- https://github.com/JaidedAI/EasyOCR, https://pypi.org/project/easyocr/
- https://tesseract-ocr.github.io/tessdoc/FAQ.html
- https://tesseract-ocr.github.io/tessdoc/ReleaseNotes.html
- https://www.codesota.com/ocr/paddleocr-vs-tesseract
- https://github.com/datalab-to/surya
- https://huggingface.co/datalab-to/chandra

Vision-language models and benchmarks
- https://huggingface.co/microsoft/Florence-2-base
- https://huggingface.co/docs/transformers/model_doc/florence2
- https://blog.roboflow.com/florence-2-ocr/
- https://inference-models.roboflow.com/models/florence2/
- https://huggingface.co/stepfun-ai/GOT-OCR-2.0-hf
- https://github.com/allenai/olmocr
- https://github.com/QwenLM/Qwen3-VL
- https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct (and its config.json)
- https://huggingface.co/api/models/Qwen/Qwen3-VL-4B-Instruct
- https://huggingface.co/api/models/Qwen/Qwen2.5-VL-3B-Instruct
- https://huggingface.co/api/models/Qwen/Qwen3.6-27B
- https://huggingface.co/api/models/nanonets/Nanonets-OCR2-3B
- https://huggingface.co/api/models/PaddlePaddle/PaddleOCR-VL
- https://huggingface.co/api/models/deepseek-ai/DeepSeek-OCR
- https://arxiv.org/html/2511.21631 (Qwen3-VL technical report)
- https://github.com/QwenLM/Qwen3-VL/issues/1231
- https://artificialanalysis.ai/articles/qwen3-5-small-models
- https://arxiv.org/html/2608.18586 (OmniHandwritingOCR)
- https://arxiv.org/abs/2503.15195 (Crosilla, Klic, Colavizza 2025)
- https://arxiv.org/abs/2601.14490 (GutenOCR)

reMarkable and MyScript
- https://support.remarkable.com/articles/Knowledge/Convert-handwritten-notes-into-text
- https://remarkable.jms1.info/info/issues.html
- https://github.com/akeil/rescript
- https://github.com/ddvk/rmapi-hwr
- https://github.com/vgmakeev/remarkable-myscript-mcp
- https://developer-support.myscript.com/support/discussions/topics/16000030978
- https://developer-support.myscript.com/support/discussions/topics/16000032738
