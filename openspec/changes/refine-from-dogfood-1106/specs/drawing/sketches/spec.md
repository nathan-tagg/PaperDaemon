## ADDED Requirements

### Requirement: A sketch can carry words
A figure the model draws part by part SHALL be able to carry words: a text part, lettered in PaperDaemon's own face
on the figure's grid like every other part, at a baseline point, anchored at its left end, its middle or its right
end, at a capital height the part names, turned by an angle when one is named. A diagram asked for with labels
SHALL have them. A line of the figure that ends inside a label's words SHALL stop a little short of them: no label
is struck through by the leader that points at it.

#### Scenario: A labeled diagram
- **WHEN** the user asks for a labeled diagram of the water cycle
- **THEN** the sketch has its shapes and arrows and a word by each stage, lettered, inside the sketch's box

#### Scenario: A text part with no words
- **WHEN** a text part names no text
- **THEN** that part is refused by name and the rest of the figure is drawn

#### Scenario: A leader into its label
- **WHEN** a line's end lands among the letters of the label it points at
- **THEN** the line ends just before the label's first letter, and the label is whole
