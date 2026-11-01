# Proposal: add-picture-paste

## Why

Every generated or found picture is drawn in pen strokes. A request to paste a picture ("Paste an image of the Mona
Lisa") got the picture decomposed, not pasted. The maintainer's ruling: a sketch asks for lines worked out from
shapes; generating a picture or showing one asks for it generated, or found on the web, and drawn in strokes; pasting
a picture asks for the picture itself on the page. No words are matched in the host: the model reads what is asked.

## What Changes

- An image step and a web_picture step take `paste: true`. The host then puts the picture on the page as the app's
  own image block, fitted to its box as a coloring page is, instead of drawing it in strokes.
- The brief describes the three by what is asked: draw is a sketch, lines from simple shapes; image and web_picture
  are drawn in strokes, or pasted as they are with `paste: true`.
- A sketch is drawn on one grid. Three live sketches of a house with a tree and the sun each went wrong: the sun left
  out, the sun drawn as a separate icon on the page's coordinates and moved onto the house's window, the window's
  cross drawn beside the house. Icons become parts of a figure, fitted with it; an icon drawn with a figure joins it;
  a figure drawn again for a fix stays in its own box. A sketch step no longer offers `image()`: a sketch makes no
  picture, and the tool, offered nowhere else, leaves the tool list.

## Impact

- Affected specs: drawing/pictures.
- Code: paperdaemon/pipeline/host/steps.py (the field and the brief's lines), paperdaemon/pipeline/host/features/
  pictures.py (`_paste_into`, used by image steps), paperdaemon/pipeline/host/features/web.py (`t_fetch`),
  paperdaemon/pipeline/host/__init__.py.
