## ADDED Requirements

### Requirement: Pictures are ordered within their layer
A selected picture in the page editor SHALL offer Bring to front, Bring forward, Send backward and Send to back, in its
right-click menu and as Ctrl+Shift+], Ctrl+], Ctrl+[ and Ctrl+Shift+[. A picture SHALL move only among the pictures of
its own layer, and a choice that would not move it SHALL be grayed out. A save SHALL write the order so the tablet
stacks the pictures that way: a layer whose pictures are reordered has every picture of it put on again as a chain in
the new order, each naming the one before it, the old items tombstones.

#### Scenario: Sent to the back
- **WHEN** the user sends the top picture of a layer with three to the back and the page is saved
- **THEN** the page reads back with that picture under the other two, on the tablet as in the editor

#### Scenario: Saved again as it was read
- **WHEN** a page whose pictures were reordered is read and saved without a change
- **THEN** nothing is written

#### Scenario: Another layer
- **WHEN** a picture is brought forward on a page whose pictures are on two layers
- **THEN** it passes only the pictures of its own layer; the other layer's stay where they are
