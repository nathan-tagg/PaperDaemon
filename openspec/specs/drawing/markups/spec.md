# drawing/markups Specification

## Purpose
Marks up the words a request names, on notebook pages and PDFs, and erases without disturbing anything
else on the page.

## Requirements

### Requirement: Mark-ups land on located words
The host SHALL highlight, circle, underline or strike the words a request names, typed or handwritten,
at their measured positions, and SHALL NOT mark up the words of the request itself.

#### Scenario: Highlight every "deadline"
- **WHEN** a page asks to highlight every "deadline" in the notes above
- **THEN** each "deadline" in the notes is highlighted, and the word in the request is not

### Requirement: PDF words are found in the PDF's text
On a PDF page, the host SHALL find the named words in the PDF's own text layer and draw the mark-up over
their positions on the page as the tablet shows it.

#### Scenario: Highlighting a PDF
- **WHEN** a request on a PDF page asks to highlight a phrase
- **THEN** the highlight covers that phrase where the tablet shows it

#### Scenario: A PDF page of another size
- **WHEN** the same request is made on a Letter-size PDF page
- **THEN** the highlight covers the phrase there too, not a spot scaled toward the page's corner

### Requirement: Erasing keeps the page's structure
Erasing SHALL mark erased strokes and characters as deleted in place, as the tablet itself does, and
SHALL NOT remove them from the page's structure, so nothing that was not erased moves.

#### Scenario: Erasing a line near anchored ink
- **WHEN** the host erases one handwritten line on a page with typed text and ink anchored to it
- **THEN** that line is gone and every other stroke and character stays where it was on the tablet
