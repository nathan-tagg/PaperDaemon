# Proposal: add-picture-order

## Why

The maintainer (11-25): "we need bring to front / send to back / bring forward / send backward controls on images ...
I'd assume they can't cross layers ... so it would be within a layer".

## What Changes

- A selected picture's right-click menu in the page editor gets Bring to front (Ctrl+Shift+]), Bring forward (Ctrl+]),
  Send backward (Ctrl+[) and Send to back (Ctrl+Shift+[), each grayed out when the picture is already there. A picture
  moves among the pictures of its own layer only; typed text stays over every picture, as on the tablet.
- The tablet stacks a layer's pictures in the order of that layer's sequence. A save that orders a layer's pictures
  otherwise puts every picture of that layer on again as a chain, each naming the one before it, so they stack in that
  order whoever wrote them. A False Mirror save writes its pictures as such a chain always.
- The editor, the renderer and the tablet read the same order: pictures linked by nothing stack by id, as before.

## Impact

- `paperdaemon/pipeline/page/images.py` (links, stacking), `paperdaemon/remarkable/local.py` (pictures in stacking
  order with their layer; a chain on a whole save), `paperdaemon/remarkable/inplace.py` (a reordered layer put on again),
  `paperdaemon/ui/editor.html` (the menu and the keys), tests in `test_false_mirror.py` and `test_mirror_inplace.py`.
