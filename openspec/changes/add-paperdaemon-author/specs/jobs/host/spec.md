## REMOVED Requirements

### Requirement: What a job writes is the tablet's own author's
**Reason**: Measured on the tablet (11-07), a page per author number from 1 to 512: it opens a page with 1-159, 175,
191, 207, 212 and 240-255, and the maintainer ruled that PaperDaemon's strokes are told apart from the user's by
their author byte, which also says what each was.
**Migration**: What PaperDaemon writes goes under its author bytes (see "PaperDaemon's strokes say whose they are
and what they were"). Items written as the tablet's author before stay as they are.

## ADDED Requirements

### Requirement: PaperDaemon's strokes say whose they are and what they were
Everything PaperDaemon writes on a page SHALL carry an author byte of 100kkkkk (128 to 159, all of which the tablet
opens): the top three bits SHALL say it is PaperDaemon's, and the low five what it was -- 1 a written answer, 2 a
picture traced into strokes, 3 a chart, calendar or table, 4 a sketch, 5 a mark-up, 6 the daemon's note, 7 a placed
picture, 8 typed text, 0 anything else. Each kind SHALL be numbered on from its own ids on the page, and the page's
author table SHALL name each byte used. PaperDaemon SHALL tell its own strokes, and what each was, by that byte
alone: nothing SHALL be kept beside the page for it, and nothing SHALL be judged PaperDaemon's by how its points
look. A picture's ids SHALL be written with their author in one byte, as the format has it.

#### Scenario: An answer lettered on a page
- **WHEN** a job writes its answer on a page
- **THEN** every new stroke is of author 129, numbered on from that author's own ids, and the page's author table
  names 129

#### Scenario: A page with an answer, a highlight and a picture
- **WHEN** one job writes an answer, highlights a word and places a picture
- **THEN** the answer's strokes are 129, the highlight's 133 and the picture's 135, and PaperDaemon reads each back as
  its own, of that kind
