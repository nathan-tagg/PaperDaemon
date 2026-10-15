# drawing/pictures Specification

## Purpose
Puts pictures on the page: generated or fetched pictures drawn in pen strokes, and coloring pages the
user can color and erase over.

## Requirements

### Requirement: Pictures are drawn in strokes
A generated or fetched picture SHALL be traced into pen strokes by the decomposer and drawn into its
planned box, keeping its aspect.

#### Scenario: A picture of a fox
- **WHEN** a page asks for a picture of a fox
- **THEN** the image slot makes it, the decomposer traces it, and the strokes fill the planned box

### Requirement: Coloring pages are inserted pictures
A coloring page SHALL be made with the image harness's `childrensColoringBook` workflow (its wording and its
steps), cleaned to pure black lines on
white with the lines thickened slightly, and inserted as a picture that takes the page, not traced, so
the user's coloring and erasing touch only the user's own ink.

#### Scenario: Coloring over it
- **WHEN** the user colors a coloring page and then erases a stroke of their own
- **THEN** the picture's lines are untouched

#### Scenario: Gray the model added anyway
- **WHEN** the image model returns a coloring page with gray shading
- **THEN** the inserted page has only black lines on white

### Requirement: Extra coloring pages go on new pages
When a job makes more than one coloring page, each extra one SHALL go on a new page after the job's page
in the same notebook.

#### Scenario: Three coloring pages
- **WHEN** a page asks for three coloring pages of farm animals
- **THEN** the first takes the job's page and the other two take two new pages after it

### Requirement: Generated pictures are not kept
PaperDaemon SHALL keep a generated picture only while the job needs it, and SHALL NOT keep copies,
previews or thumbnails of it afterward, beyond what is on the tablet.

#### Scenario: After a job
- **WHEN** a job that generated a picture finishes
- **THEN** no copy of the picture remains in PaperDaemon's data folder
