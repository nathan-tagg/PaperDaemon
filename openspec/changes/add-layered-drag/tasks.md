## 1. Measure

- [x] 1.1 Each stage of a drag's frame on the integrated card (marks, move, draw by class), small, medium and large
  selections on the maintainer's heaviest page, in ms a frame (design: Measured)
- [x] 1.2 The maintainer's ruling on big selections: exact every frame, below 60 a second when the card cannot draw the
  selection faster; every other cost cut first
- [x] 1.3 Cut, exact (0 pixels against a whole redraw): the moved blocks boxed as their own ranges, found by a binary
  search (they were boxed as one range from the first to the last, nearly every block of the page, when they ran to
  more than 256); the move's box worked out from the frame's matrix (two passes over every selected record a frame
  gone). Small selection 19.8 -> 12.5-14.4 ms a frame; medium (39,750 strokes, the first drag on the page) 60.8 ->
  50.3 ms
- [x] 1.4 After one drag let go and undone, each input waits about 5 s: the bench's own (an off-screen page with nothing
  moving draws no frames, and input waits for one); the rigs keep frames coming
- [x] 1.5 Undo after a drag left pieces where the drag had put them (the maintainer's demo notebook: the decomposition
  selected, its highlighters kept, moved, undone: 24,228 pixels left, a whole redraw drawing them again). A stroke drawn
  anew on landing (its points' count changed) kept its old part, whose records on the card were the moved ones; an undo
  brought it back with them. Its records are put back once it is swapped out (moveRestore): 0 pixels
- [ ] 1.6 That undo takes 1.4 s on the 150,000-stroke page on the integrated card

## 2. Layers

- [ ] 2.1 The page's draws limited to a span of its order (before, between, after)
- [ ] 2.2 Taken up: the before picture, the after colors and their mask
- [ ] 2.3 Each frame: the before picture where the selection was and is, the between span over it, the after span's
  highlighters and grain and washes over that, the fixed after colors last
- [ ] 2.4 Let go or put back: the textures freed; the fallbacks (view moved, card lost, a stroke cut)

## 3. Proof

- [ ] 3.1 Every frame against a whole draw, 0 pixels different, in the cases of D7
- [ ] 3.2 Each stage's time on the integrated card, before and after
