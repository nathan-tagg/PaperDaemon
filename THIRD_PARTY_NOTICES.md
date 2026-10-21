# Third-party notices

PaperDaemon is licensed under the Apache License 2.0. It includes or ships with the following components,
each under its own license.

## Shipped beside PaperDaemon

- **Stockfish 19** (GNU General Public License version 3), the chess engine. The official Windows x86-64
  build, unchanged, is placed in the app's `engine/stockfish` folder by `tools/build_app.py` and runs as a
  separate program. Its license (`Copying.txt`), authors and a link to its source
  (<https://github.com/official-stockfish/Stockfish/tree/sf_19>) are in that folder.

## In the source tree

- **The C decomposer's vendored and ported code** (Pillow, stb_image, libjpeg-turbo, x86-simd-sort, LLVM
  libc++, and algorithms ported from numpy, OpenCV and scikit-image): see
  `paperdaemon/pipeline/decompose/fastdecomp/THIRD_PARTY_NOTICES.txt` and the license files under its
  `vendor/` folder. This software is based in part on the work of the Independent JPEG Group.
- **Source Sans 3, Source Serif 4 and Source Code Pro** (SIL Open Font License 1.1, Adobe), the interface's
  fonts: `paperdaemon/ui/fonts/*/LICENSE.md`.
- **GeoNames** (Creative Commons Attribution 4.0, <https://www.geonames.org>), the city list behind the
  Location control: `paperdaemon/content/places/cities.tsv.gz`, built from GeoNames' cities15000, admin1 codes
  and country info by `tools/build_places.py` (fields selected and rounded; nothing else changed).
- **GNHK**, the GoodNotes Handwriting Kollection (Creative Commons Attribution 4.0): twelve pages of its test
  set in `paperdaemon/content/handwriting`, for the Test tab's handwriting test (turned upright, scaled,
  re-saved without camera metadata; see that folder's README).
- **Lucide** (ISC License, Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of
  Feather (MIT); all other copyright (c) for Lucide are held by Lucide Contributors 2022,
  <https://lucide.dev>): the icon outlines in `paperdaemon/pipeline/charts/icons.py`, flattened to one path
  per icon and moved onto a unit box. Permission to use, copy, modify, and/or distribute this software for any
  purpose with or without fee is hereby granted, provided that the above copyright notice and this permission
  notice appear in all copies.
- **The "cburnett" chess pieces** by Colin M.L. Burnett (Creative Commons Attribution-ShareAlike 3.0,
  <https://creativecommons.org/licenses/by-sa/3.0/>), as published by Lichess
  (<https://github.com/lichess-org/lila/tree/master/public/piece/cburnett>): the twelve piece drawings in
  `paperdaemon/content/games/pieces/cburnett`, unchanged. PaperDaemon recolors them to its board when it draws
  them; the drawings and the piece pictures made from them stay under CC BY-SA 3.0 (see that folder's
  `LICENSE.md`).
- **The System Reference Document 5.1** by Wizards of the Coast LLC (Creative Commons Attribution 4.0,
  <https://dnd.wizards.com/resources/systems-reference-document>): the Ink Adventure's ability, skill, class,
  race, armor and spell names and rules in `paperdaemon/pipeline/games/adventure.py`, a small subset, reworded
  into data. This work includes material taken from the System Reference Document 5.1 ("SRD 5.1") by Wizards
  of the Coast LLC.
- **Noto Sans, Noto Sans Mono and Noto Sans Hebrew** (SIL Open Font License 1.1, The Noto Project Authors,
  <https://github.com/notofonts>), the tablet's own versions (2.015, 2.014, 3.001 full), unchanged, for laying out
  books as the tablet does: `paperdaemon/content/book-fonts/noto` with `OFL.txt`.
- **EB Garamond** (SIL Open Font License 1.1, The EB Garamond Project Authors, <https://github.com/google/fonts>),
  the published variable font, unchanged, for books when the reMarkable desktop app's own build is not on the
  computer: `paperdaemon/content/book-fonts/eb-garamond` with `OFL.txt`.
- **Arimo and Gelasio** (SIL Open Font License 1.1, <https://github.com/google/fonts>), PaperDaemon's own faces for
  typed text: fixed Regular, Bold, Italic and Bold Italic cut from the published variable fonts with fontTools'
  instancer, in `paperdaemon/content/typed-fonts` with each family's `OFL.txt`.
- **OpenSpec** (MIT, <https://github.com/Fission-AI/OpenSpec>): the specifications in `openspec/` are written in
  its format and checked with its command-line tool. It is a development tool and is not part of the app.

## Bundled into the app

- **The engine's Python packages**, frozen with PyInstaller (GPL-2.0 with its bootloader exception): FastAPI,
  Uvicorn, keyring, pywebview, Pillow, NumPy, rmscene, fontTools, jsonschema, pypdfium2 (PDFium), vl-convert,
  the Windows Runtime projections, httpx, holidays and their dependencies, each under its own license (MIT,
  BSD, Apache-2.0, HPND or similar). Their license files are gathered into the app's `engine/licenses` folder
  at build time. The packages the decomposer's Python reference runs on (Numba, OpenCV, SciPy, scikit-image,
  Shapely) are development dependencies only and are left out of the app.
- **ANGLE** (BSD-3-Clause, The ANGLE Project Authors, <https://chromium.googlesource.com/angle/angle>): OpenGL ES 3
  on Direct3D 11, through which the engine draws its pictures of pages on the graphics card
  (`paperdaemon/pipeline/page/gpu.py`) with the page editor's own shaders (`paperdaemon/ui/shaders.js`) -- the page
  editor draws through WebView2's ANGLE, the engine through this copy. Built from source at a pinned commit by
  `tools/build_angle.py` (Direct3D 11 only): `libEGL.dll` and `libGLESv2.dll`, shipped unmodified in the app's
  `paperdaemon/pipeline/page/angle` folder with ANGLE's `LICENSE`.
- **Qt for Python (PySide6-Essentials) and Qt 6.10.3** (GNU Lesser General Public License version 3, The Qt
  Company), which lay books out as the tablet lays them out: shipped as the unmodified libraries of the published
  wheel, loaded at run time, so they can be replaced with another build of the same version. Their license files are
  in the app's `engine/licenses` folder; Qt's source is at <https://download.qt.io/official_releases/qt/>.
- **The desktop shell**: Tauri 2 and its Rust crates (MIT or Apache-2.0), Microsoft's WebView2 runtime
  bootstrapper, and the installer made with NSIS (zlib license) and nsis-tauri-utils (MIT or Apache-2.0).
