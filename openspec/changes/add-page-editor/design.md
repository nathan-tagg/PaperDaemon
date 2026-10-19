# Design: add-page-editor

## Context

Everything below was measured on the maintainer's Paper Pro, through the tablet's own screen share and
the page files it synced, on 2026-10-17 and 2026-10-18. Test pages were made in every frame reMarkable
uses (1404 x 1872, 1620 x 2160, 954 x 1696) and two no tablet makes (3240 x 4320 and 200 x 266). Where a
finding is an inference rather than a measurement, it says so.

## Findings

### F1. Page units are fixed

A page's coordinates are fixed units: on the Paper Pro at 1x, one unit is one screen pixel (about 0.11 mm
at 229 pixels per inch). Stroke widths, text sizes, line spacing and the typed-text columns are the same
number of units on every frame. A bigger frame adds paper around the content; it never scales it.

### F2. The drawable square

A page's drawable area is a square as wide as the page is tall, centered on the page's center line
(x from -h/2 to +h/2), from y 0 down. The tablet will not start a stroke outside it. A stroke started
inside keeps the points it draws outside: they are stored, and not shown. The page extends downward past
its frame height to hold content below it. Measured: the 0.5x view of a 2160-tall page shows a white
band about 2170 units wide; the 200 x 266 page shows about 272.

### F3. Typed text

- All typed text on a page is one block with one column: x and width. The column setting applies to the
  whole page.
- Three columns, each centered on the page's center line, the same on every frame: wide x -576, width
  1152; medium x -468, width 936; narrow x -370, width 740. The library holds 275 wide, 75 medium and 2
  narrow pages; the screen share placed each column's edges at exactly these numbers on the Paper Pure,
  Paper Pro and 3240 x 4320 frames.
- The text starts at y 234. Text is laid out in the full column on every frame and clipped at the drawable
  square's edges like ink: on the 200 x 266 page its lines are cut mid-letter at both edges, and the
  paragraph handle stands out in the gray where the full column begins.
- Spacing measured on screen agrees with `typed.py`: body lines about 46 units apart (the layout uses
  45), a paragraph step of about 70 (45 + 25), the title's lines about 76.
- Four text styles, largest first: Title (large serif), Header (medium serif, lines about 56 apart),
  Section (small bold sans, about 41) and Body (sans, about 46). Bullets, numbers and checkboxes exist
  only in Body: a bulleted paragraph changed to Header loses its bullet.
- Checking a checkbox fills the box with a white tick and strikes through every line of its paragraph.
- Space below a drawing is made with empty paragraphs; the tablet anchors strokes drawn beside text to a
  paragraph, moves them with it, and deletes them with it.

### F4. Pens, sizes and colors on the tablet

- Two pen pickers in the toolbar, each showing its pen's head and a colored dot at its top right; the
  tool in hand is shown inverted. Tapping the one in hand opens its menu.
- The menu: the pen's name, nine pen heads in a 3 x 3 grid (ballpoint, fineliner, highlighter; pencil,
  mechanical pencil, calligraphy; marker, shader, paintbrush; the marker and paintbrush places are
  inferred), a size section titled with the size's name and three slanted strokes, and the colors.
- Pens other than the highlighter and shader: nine colors in a 3 x 3 grid, each a dot over its name:
  black, gray, white; blue, red, green; yellow, cyan, magenta. The dots are pure colors (blue 0,0,255,
  red 255,0,0, gray 148,146,148), and the desktop app draws red ink as 255,0,0.
- Highlighter: no size; six colors in two rows: yellow, blue, pink; orange, green, gray. Sampled on
  screen within 5 of the highlighter table in `render.py`; orange 255,195,140.
- Shader: sizes; eight colors: gray, orange, magenta; blue, red, green; yellow, cyan. Each dot is split,
  a lighter top half over a darker bottom half (about 0.6 of it), one coat over overlapping coats. The top
  halves match the pen color table in `render.py` (blue 49,73,231 against 48,74,224; red 198,48,49
  against 194,49,50); orange 255,178,0. A single coat on the page is a light wash, and overlapping
  strokes darken.
- Pens are opaque: a later stroke covers an earlier one.
- The text tool's menu: Add text (Edit text once the page has text) and the three column widths. Editing
  shows a keyboard with undo, redo, the four styles and the three list types.

### F6. Templates

- The layers list ends with Text and Template, each with its eye; Template's row has a button that opens
  "Choose template": tabs Default and rM Methods, a filter (All), and a grid of icons, five across, each
  over its name, the page's template underlined. The defaults run alphabetically (Blank, Bass tabs,
  Calligraphy large, Calligraphy medium, Checklist, Cornell, Day planner, the Dots, Grid and Hexagon
  families, Isometric, ...).
- The desktop app's program file carries, in its Qt resources (some packed: a 4-byte length, then zlib):
  - `templates.json`, the index: each template's name, its file name (`P ...` portrait, `LS ...`
    landscape), categories, and an `iconCode`;
  - the template definitions, vector and parametric: JSON with constants (`gridSize: 78.3`, expressions
    over `templateWidth` and `templateHeight`) and items, groups of paths that repeat across or down the
    page;
  - the icon font (icomoon): each `iconCode` is a glyph in it, and drawn they are the tablet's picker
    icons exactly.
- Read on 2026-10-18: every portrait template but six has a definition (`Grid margin`, `Lined medium` and
  `Lined small` are stored as `Grid margin medium`, `Lines medium`, `Lines small`). Blank is empty paper;
  Calligraphy large and medium and Hexagon large, medium and small have no data: the app draws them in
  its own code (`SceneTemplateRenderer` types), so PaperDaemon draws those five itself, matched to the
  tablet.
- PaperDaemon is portrait only: the landscape (`LS`) templates are left out.
- rM Methods templates sync as documents of their own, of type `TemplateType` (`source`
  `com.remarkable.methods`): a JSON body with the name, the author and the icon as base64 SVG. The
  user's library holds five.
- A page names its template in the document's `.content`; the page file holds only whether it is shown.

### F5. Opening zoom

Every document's `.content` stores `zoomMode: bestFit`, and the page info is the same on pages that open
at different zooms. The opening zoom the tablet shows is remembered on the tablet, not in the files.

## Decisions

- **D1. The editor writes real page data.** A page in the editor is a SceneInfo with its frame, Layer 1,
  and lines as the file stores them: pen, color, thickness scale, color RGBA, item id, and per point x,
  y, speed, direction, width and pressure. Every pen is held upright at 50% pressure (128 of 255).
- **D2. The editor draws with PaperDaemon's renderer.** The rasterizer in `fastdecomp/render.c` and the
  stroke preparation in `render.py`, ported unchanged, so the editor shows what PaperDaemon renders.
- **D3. Open: the pens' ink colors.** The renderer draws pens in the shader's palette (F4); the tablet's
  pens are pure colors. The editor keeps the renderer's table until the maintainer decides; its menus
  show the tablet's swatches.
- **D4. Text and ink are two layers.** The editor does not anchor strokes to paragraphs and does not move
  either for the other. Deleting text never deletes ink. If an edit removes the paragraph a stored group
  of strokes is anchored to, the editor rewrites those strokes unanchored where they were shown. Reading
  pages the tablet made still resolves its anchors.
- **D5. Typing just starts.** No Add text button, and no tool to choose first: a key that types puts the
  cursor at the end of the text while the pen in hand keeps drawing. With the text tool, a click below
  the text adds empty paragraphs down to that line, a click in it places the cursor. Styles, lists, bold,
  italic, cut, copy, paste and word deletion (Ctrl+Backspace, Ctrl+Delete, the same with Shift) are
  keyboard shortcuts; there is no selection bar.
- **D6. Open: style codes.** The file stores BASIC, PLAIN, HEADING and BOLD; the tablet offers Title,
  Header, Section and Body. Title is HEADING and Body is PLAIN by their measured sizes; which code Header
  and Section write is read from the next synced test page. Until then the editor writes Header as BASIC
  and Section as BOLD, and draws Header from screen measurements (serif, about 48 units, lines 56 apart).
- **D7. No snap to text, no selection-erase.** The highlighter's snap to text is left out, and erasing
  whole strokes stands in for the tablet's circle-to-erase.
- **D8. A fallback face.** Where the user's desktop app is missing, typed text is drawn in an openly
  licensed family chosen by measuring its advance widths against the tablet's faces, so lines wrap where
  the tablet wraps them. The window says when it is drawing the fallback.
- **D9. Layers.** The layers control lists the page's layer nodes; the pens and the eraser work on the
  one in hand, as on the tablet. A stroke drawn under a visible layer shows on top until it is finished,
  then takes its place under it, as the tablet itself shows it.

- **D10. Templates are borrowed, never shipped, and never content.** Like the fonts, the default
  templates and their icons come from the user's own desktop app, and rM Methods templates from the
  user's library. Before a template is drawn under anything the host or a model sees, every part that
  reads a page must treat it as background: the render a model is shown, the free-space and safe-area
  layout, the marks and erase grounding, OCR, the decomposer's input, and the harnesses' and lineups'
  page descriptions (which may name the template). A template line is never a stroke to find, erase,
  answer under or avoid.

## Risks

- The text layout is calibrated on a few pages; an edited page may wrap a word differently from the
  tablet. The layout keeps reporting itself approximate.
- Stored widths for the ballpoint, both pencils, paintbrush, calligraphy pen and shader are placeholders
  until strokes of each are read from a synced page; how they are drawn is the renderer's.
