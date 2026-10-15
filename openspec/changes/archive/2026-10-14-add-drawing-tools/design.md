# Design

## Context

See proposal.md for why. The pipeline modules this change ports were each tuned on real pages:
`typed_layout` measures the tablet's real typeface faces, `rm_chart` renders Vega-Lite through
`vl-convert` with styling that keeps charts to two or three colors with no blended pixels, `rm_images`
writes the same picture blocks the tablet writes for a capture, and `rm_paint` (the decomposer, about
3,200 lines) is a frozen engine.

## Goals / Non-Goals

**Goals:**
- Port with parity; each tool keeps its measured behavior.
- Remove everything personal from the code while porting: locations, notebook names, incident notes.

**Non-Goals:**
- Improving the decomposer, the chart styling or the typeface model. Parity first.

## Decisions

**Charts are Vega-Lite rendered by `vl-convert`.** Chosen in the pipeline on measurements over matplotlib,
plotly, pygal and gnuplot: one wheel, no browser, no network, and crisp output once both
`shape-rendering="crispEdges"` and `text-rendering="optimizeSpeed"` are set. Two traps are kept as
tests: Vega-Lite sorts nominal categories alphabetically unless every chart pins its order, and
`vl-convert` silently drops all text in a font it lacks, so the font is checked at start.

**Charts go on as pictures.** The chart's render is inserted as a picture block, the same kind the tablet
writes when the user places a picture. The pipeline's alternative paths (tracing, or drawing the chart's SVG
parts as strokes) stay available as an option but are not the default.

**The typeface comes from the user's machine.** The reMarkable app's font files are not ours to ship.
PaperDaemon looks for them in the user's reMarkable desktop app installation and measures from them; with no
installation, it uses an openly licensed typeface with close metrics. Answers are drawn as strokes, so
no font is ever sent to the tablet.

**The decomposer is copied, not rewritten.** `rm_paint` moves into `paperdaemon/draw/decomposer/` unchanged
apart from imports and comments, and a golden test compares its strokes with the pipeline's engine on a fixed
set of pictures. Any change to its output fails that test until the maintainer approves the new golden set.

**One renderer, two framings.** the pipeline's `rm_render` moves into `paperdaemon/draw/render.py`. It draws
a page the way the tablet shows it: ink with the tablet's pens and widths, typed text in the app's
faces, pictures, and anchored items where the tablet puts them. It frames the result two ways, from the
same code:
- the whole tablet page: the intake's page image, the benchmark's result pages, the overview
- cropped to the ink: the decompose preview

The reader's image for handwriting recognition is a different thing on purpose (every stroke at one
width, black on white) and stays in the reader.

**A PDF page is its own frame.** The tablet lays a PDF page's ink at a fixed 1404 units to 157.5 mm
(3.1447 units per point), whatever the page's size, with x = 0 at the page's center and y = 0 at its
top. The SceneInfo of every PDF page says 1404 × 1872, and that is not the frame. Fitting the PDF into
1404 × 1872 agrees with the tablet only at 157.5 × 210 mm, the one size the pipeline had checked; everywhere
else it put the page image, highlights and pointed-at spots off by the ratio of the sizes, until
2026-09-27. How the tablet shows a page (zoom, scroll) does not move its ink. One function gives a
page's frame, and the renderer, the PDF word finder, the page image's pixel mapping and the safe area
all take it from there.

**Erasing uses tombstones.** A deleted stroke keeps its item and links with its value cleared, as the
tablet's own erasures do; a deleted typed character keeps its item with its deleted length set.
Removing items outright would leave dangling links and let the app re-lay-out anchored groups.

**Coloring pages are cleaned and inserted.** Anything darker than a threshold becomes black, the rest
white, and lines are thickened a little so a crayon stays inside them. The maintainer's rule decides between
inserting and tracing: if the user will draw and erase on it, insert it.

## Risks / Trade-offs

- [The substitute typeface's metrics differ from the tablet's] → Measure and choose the substitute on
  real pages; the column and line spacing come from the page file, not the font.
- [The golden test pins the decomposer to the pipeline's exact output on one machine] → Pin numpy and Pillow
  versions with it; a platform difference is reported, not papered over.
- [Pictures anchored to text move when the user types] → Placements are recorded at commit, as the pipeline
  does, so a later job reads a picture's true position.

## Open Questions

Can wait:
- Which openly licensed typeface is the substitute.
- Whether the strokes path for charts should be offered in the settings.
- Whether coloring pages should also be offered as documents.
