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
