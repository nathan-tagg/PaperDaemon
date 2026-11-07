# Proposal: refine-from-dogfood-1106

## Why

The maintainer asked for constant dogfooding with real work, every result checked in the viewer, and each fix
released as it is found. The 11-06 rounds (DF51-DF83, and a chess game against Barty) turned up defects that each
sit in one place: the host's runaway guard read a chart's average line as a loop; the model worked a trend line out
by itself and got its direction wrong; a plan of several additions to one drawing was refused as overlapping; the
brief let a question that also says how to answer be ruled a request and erased; additions to a drawing were fitted
into a box beside it; a redone coloring page kept the old one under it; the lettering wrote "6½" as "61/2" and lost
"≈"; and the chess reader took a written "c3" for Nc3 and the opponent's own words in the talk strip for the
player's.

## What Changes

- A chart's trend and average lines are the host's: `trend: true` / `average: true` on a line, step or bar chart,
  fitted and drawn by the host (dashed, dotted, named at their ends), and the words about a chart get the fitted
  trend among the host's figures.
- The runaway guard takes a chunk repeated back to back as a loop only over 400 characters (and six times), so a
  constant data series is data.
- Places drawn onto one mark ("on" it) may share it: hat, scarf and buttons all go on one snowman.
- The brief: a question stays even when it says how to answer; only a pure instruction comes off; the facts and
  numbers a request works from are the user's notes. An addition to a drawing goes on that drawing's mark.
- A picture that lands over most of an old one replaces it, for coloring pages and pasted pictures as for charts.
- The lettering draws fractions, superscripts, subscripts and ≈ ± × ÷ √ ∞ π µ as themselves.
- Chess: the reader is shown the player's ink alone, copies it, and a copy in chess notation is played as written.

## Impact

- Code: `pipeline/host/model.py`, `layout.py`, `__init__.py` (brief), `features/chart.py`, `features/pictures.py`;
  `pipeline/charts`; `pipeline/draw/symbols.py` (new), `lettering.py`; `pipeline/games/__init__.py`, `inputarea.py`.
- No settings, no new dependencies, nothing about the tablet or the cloud.
