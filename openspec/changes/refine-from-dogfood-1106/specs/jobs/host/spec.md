## ADDED Requirements

### Requirement: A chart's data is not a loop
The host SHALL take a model's output for a loop only when one chunk repeats back to back at least six times and
over at least 400 characters. A short value repeated in a chart's data (a constant series, an average line typed as
equal numbers) SHALL NOT stop the turn.

#### Scenario: A year of weeks at one value
- **WHEN** a chart step's series holds the same number 52 times
- **THEN** the turn is not stopped, and the chart is drawn

#### Scenario: A real loop
- **WHEN** a tool call's arguments repeat "0, " two hundred times
- **THEN** the host stops the turn as a loop

### Requirement: Additions onto one drawing share it
Places the model puts ON a mark on the page (`side: "on"`) SHALL NOT be refused for overlapping each other: each
is the drawing it goes on, not new room. Every other place SHALL still keep clear of everything.

#### Scenario: A hat, a scarf and buttons for the snowman
- **WHEN** a plan has three draw steps, each near the snowman's mark with side "on"
- **THEN** the plan is accepted, and each addition is drawn on the snowman

### Requirement: A picture placed over an old one replaces it
A picture that lands over most (40%) of a picture already on the page SHALL take that picture's place: the old one
comes off when the new one lands. This SHALL hold for charts, coloring pages and pasted pictures alike.

#### Scenario: A coloring page made again
- **WHEN** the user asks for a coloring page to be redone, and the new one lands where the old one was
- **THEN** the page holds only the new coloring page

### Requirement: An addition to a drawing is drawn on its parts and stays where it is drawn
A step that draws on a drawing already on the page SHALL be told the drawing's parts (the boxes of its biggest
strokes, top to bottom) and SHALL draw in the page's own numbers. What it draws near the drawing (within the
drawing's own size of it) SHALL stay exactly where it was drawn, never scaled, moved only as far as needed to stay on
the page. Only a figure far from the drawing, made on a grid of its own, SHALL be fitted into the drawing's box.

#### Scenario: A top hat for the snowman
- **WHEN** the model draws a hat above the snowman's head, outside the snowman's own box
- **THEN** the hat stays on the head, at the size it was drawn

### Requirement: A plan hears all its problems at once
A plan refused for its fields or rulings SHALL also be told what its steps would be refused for, in the same reply,
so it can be fixed in one turn. A circle, highlight, underline or strike that names neither the id it is in, nor the
words, nor where it is SHALL be refused before anything runs.

#### Scenario: A circle described only in words
- **WHEN** a plan's circle step says "circle the word 'Vienna' in the first answer paragraph" with no target or words
- **THEN** the plan is refused with what the step needs, and nothing has run

### Requirement: A reply goes under what it answers
A written reply SHALL start right under the lowest item it answers that stays on the page (a typed paragraph, a
handwritten line) when the free paper there, down to the next thing on the page, holds the whole reply; otherwise it
SHALL go below everything, as before. A chart a plan gave its spec SHALL be drawn from that spec without a turn of
its own.

#### Scenario: A question at the top, a note at the foot
- **WHEN** a typed question sits at the top of a page, a note to someone sits near its foot, and the answer fits in
  the paper between them
- **THEN** the answer is written right under the question, and the note stays below it, untouched

### Requirement: A reply moved under its question is checked where it is
When a reply is written under what it answers instead of in the box its plan gave it, the plan's box SHALL move with
the words, so every check of the plan afterward looks where they are.

#### Scenario: An answer above a note at the foot of the page
- **WHEN** the reply to a question is written under the question, above a note at the page's foot
- **THEN** the job is done, with no "failed" receipt and no retry box

### Requirement: A ring round words keeps off what is around them
A circle round words SHALL keep to the free paper round them: its top and bottom no nearer than a few units to the
words or ink over and under it, and its ends inside the gap beside the words, flattened as needed, the marked words
still all inside it. On open paper the ring SHALL be the ring it always was.

#### Scenario: A date that wraps in a paragraph
- **WHEN** a date that runs over two lines of a paragraph is circled
- **THEN** neither ring crosses a word that is not part of the date, and no ring's edge runs through the line above

### Requirement: A skipped page's note is plain words
The note a skipped page carries SHALL say why in plain words: it is shown on the page, so it SHALL NOT name the
page's ids (line:1, mark:11, para:2).

#### Scenario: A note to someone else
- **WHEN** a page's new handwriting is a note to someone else and the job skips it
- **THEN** the receipt says the note is addressed to that person, with no ids

### Requirement: An update waits for the old app's files
The installer SHALL wait, a few seconds at most, for the old app's executables to be free to write before it copies
the new ones, so an update started while the old app is still closing never stops on a file-in-use error.

#### Scenario: The old app is still closing
- **WHEN** an update's installer starts while the old PaperDaemon is still letting go of its executable
- **THEN** the installer waits for it and installs without asking anything

### Requirement: The request comes off with its numbers; the user's other paragraphs stay
A typed paragraph that asks for the work SHALL come off once the work is on the page, the numbers or data it works
from included when they are in that paragraph; the user's other paragraphs SHALL stay, and which paragraphs are the
request is judged from the page.

#### Scenario: Numbers and "make a chart" in one paragraph
- **WHEN** the user types "Reading minutes this week. Mia: Mon 20, ... Make a line chart of both." as one paragraph
- **THEN** the chart is drawn and that paragraph comes off

### Requirement: A word alone on its line is a line of handwriting
The page listing SHALL list a word of the user's handwriting alone on its line as a line of handwriting, with its
reading, like any other line; ink that reads as no word SHALL stay a mark.

#### Scenario: A grocery list with a one-word item
- **WHEN** the page holds "eggs", "rye bread" and "2 lemons" in ink, one item a line
- **THEN** the listing names three lines of handwriting, and "eggs" carries no stroke count beside it

### Requirement: A question answered in words stays
The host SHALL refuse a decision that rules a typed paragraph with a question mark a request or command to erase
when the job answers it in words (an answer, or a write step); a question the job answers some other way is the
request it reads as ("Can you draw a cat?" comes off once the cat is drawn).

#### Scenario: A question with an instruction on the answer's form
- **WHEN** a ruling erases "What should I pack for winter camping? Give me a checklist." and the job answers it in words
- **THEN** the decision is refused: the question stays


### Requirement: A typed list asked to be a checklist takes the tablet's own checkboxes
When the user asks for their own typed list to be a checklist, the plan SHALL have a checkbox step naming the list's
typed paragraphs, and at commit those paragraphs SHALL take the tablet's own checkbox style (ticked when the step
says checked), where they are; the list SHALL NOT be drawn again beside itself. Only typed paragraphs SHALL be
targets, and a target SHALL never be one the plan has come off the page. The style SHALL be stamped as PaperDaemon's
typed text, one past the stamp it replaces: newer than that style, and older than what the user does on the tablet
afterwards, which the tablet stamps with the page's next item number. Measured on the tablet (11-07): boxes
PaperDaemon set were ticked and unticked there, and the user's change stayed.

#### Scenario: The user ticks a box PaperDaemon made
- **WHEN** PaperDaemon has made a typed list into checkboxes and the user ticks one on the tablet
- **THEN** the box stays ticked, and the tablet's stamp on it is newer than PaperDaemon's

#### Scenario: "Make these a checklist" under a typed list
- **WHEN** the user types "milk", "eggs" and "bread" as paragraphs and writes "make these a checklist" under them
- **THEN** the three paragraphs become the tablet's checkboxes, the request comes off, and nothing is drawn

#### Scenario: A checkbox on handwriting
- **WHEN** a plan's checkbox step names a line of handwriting
- **THEN** the plan is refused: only typed paragraphs take the tablet's checkboxes
