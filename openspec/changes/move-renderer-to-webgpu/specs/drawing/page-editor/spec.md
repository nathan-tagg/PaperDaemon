## ADDED Requirements

### Requirement: The page is drawn with WebGPU
The editor SHALL draw the page on the graphics card with WebGPU: in its full mode on a card with Direct3D 12, in
its compatibility mode on a card with only Direct3D 11, chosen without telling the user which. A machine without
WebGPU SHALL have its pages drawn on the processor. The editor SHALL NOT draw with WebGL. The shaders SHALL be one
source, read by the editor and by the engine, and the engine's pictures SHALL be drawn as the editor draws them,
pixel for pixel.

#### Scenario: A card with only Direct3D 11
- **WHEN** the editor opens a page on a card that has Direct3D 11 but not Direct3D 12
- **THEN** the page is drawn on the card, exactly as on a Direct3D 12 card, and nothing asks the user anything

#### Scenario: No WebGPU
- **WHEN** the editor opens a page on a machine whose card cannot run WebGPU
- **THEN** the page is drawn on the processor, the same pixels, slower

### Requirement: A frame's work is done on the card
Every job the editor does per frame, per stroke, per segment or per pixel SHALL be done on the graphics card:
drawing, deciding which segments can reach what is drawn again, the eraser's test of each segment, what is left
of each stroke it cuts, and drawing that. Drawing part of the page SHALL touch only the segments that can reach
it. A stroke the eraser is done cutting SHALL be made its pieces on the card as the swipe goes, each a stroke of
its own in the page's order where the stroke was, and the processor SHALL take what the card made as it goes and
make the pieces written to the file from it, so that letting the swipe go leaves only what the eraser was last over.

#### Scenario: Erasing on an integrated card
- **WHEN** the user flicks the passing eraser across a page of thirty thousand strokes on a machine with only an
  integrated card
- **THEN** each frame's erase is worked out and drawn on the card, every frame shows what a full redraw shows, and
  what is saved when the swipe ends is what was shown

### Requirement: The viewport's resolution
The working canvas SHALL be the viewport's resolution, or the tablet's resolution of what is shown where that is
finer; it SHALL never be coarser than the tablet's, and never finer than both. Zooming in SHALL NOT make the card
hold more of the page than the view shows.

#### Scenario: Zoomed in
- **WHEN** the user zooms a page in to twice its size
- **THEN** the page is drawn at the viewport's resolution and the card holds no more of it than at the size before

### Requirement: Graphics memory
With a page of up to 250,000 strokes open, the editor SHALL hold no more than 200 MB of the graphics card's
memory.

#### Scenario: The largest page
- **WHEN** the user opens a page of 250,000 strokes and erases across it
- **THEN** the editor's share of the card's memory stays at or under 200 MB
