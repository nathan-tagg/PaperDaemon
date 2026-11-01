## MODIFIED Requirements

### Requirement: Pictures are drawn in strokes
A generated or fetched picture SHALL be traced into pen strokes by the decomposer and drawn into its
planned box, keeping its aspect, unless its step asks for it pasted.

#### Scenario: A picture of a fox
- **WHEN** a page asks for a picture of a fox
- **THEN** the image slot makes it, the decomposer traces it, and the strokes fill the planned box

## ADDED Requirements

### Requirement: A picture asked to be pasted is placed as itself
A generated or fetched picture whose step has `paste: true` SHALL be put on the page as the app's own image block,
fitted inside its planned box with its aspect kept, and SHALL NOT be traced into strokes. The model sets `paste`
from what the user asks; the host matches no words.

#### Scenario: Paste an image of the Mona Lisa
- **WHEN** a page asks to paste an image of the Mona Lisa
- **THEN** the picture is found on the web and placed on the page as a picture, with no strokes drawn from it

#### Scenario: A sketch
- **WHEN** a page asks for a sketch of a house
- **THEN** it is drawn as lines from simple shapes, with no picture generated

### Requirement: A sketch is drawn on one grid
A sketch SHALL be drawn from shapes and icons the model states, never from a generated picture: a picture that must
look real is an image step of the plan. The host SHALL fit the whole sketch into its box at once, its icons among its
parts; an icon drawn in the same reply as the figure, or while the figure is shown back for a fix, SHALL join the
figure and be fitted with it, and a figure drawn again SHALL stay in its own box.

#### Scenario: The sun beside the house
- **WHEN** the model draws a house as a figure and, in the same reply, a sun icon up and to the right of it
- **THEN** the sun lands up and to the right of the house, both inside the sketch's box

#### Scenario: A sketch makes no picture
- **WHEN** a sketch step is worked
- **THEN** the model is offered shapes and icons only, and no picture is generated for it
