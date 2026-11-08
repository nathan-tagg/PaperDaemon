## ADDED Requirements

### Requirement: A PDF's or a book's text can be selected and copied
With the pointer (the text tool) in hand on a page of a PDF or a book, a drag SHALL select the document's own text from the
character under the press to the character under the pointer, in reading order, and Ctrl+C SHALL copy the
selected text. Selecting SHALL write nothing to the page.

#### Scenario: Copying a sentence from a PDF
- **WHEN** the user, holding the pointer, drags across a sentence of a PDF page and presses Ctrl+C
- **THEN** that sentence's text is on the clipboard and the page is unchanged

### Requirement: A PDF's or a book's links are followed
A page's links (another page of the document, or a web address) SHALL be followed as a browser follows them. With the
pointer in hand and no key held, the pointer SHALL be the hand over a link and a click there SHALL follow it: the viewer
turns to that page, or the address opens in the browser; a drag that starts on a link SHALL be the I-beam and select the
text, following nothing. With a pen or an eraser in hand a press SHALL draw or erase as anywhere else, Ctrl and a click
SHALL follow the link, and the pointer over a link SHALL say so ("Ctrl + click to follow the link"). A link that would
be followed SHALL be shown: a light yellow box over it while the pointer is on it, a darker one while it is pressed,
and none once the pointer leaves it or the press becomes a drag.

#### Scenario: A link in a PDF's contents
- **WHEN** the user, holding the pointer, clicks a contents line that links to page 3
- **THEN** the viewer turns to page 3, and nothing is written to the page

#### Scenario: Selecting a link's words
- **WHEN** the user, holding the pointer, drags from a link across its words
- **THEN** the words are selected and the viewer stays on the page

#### Scenario: A pen over a link
- **WHEN** the user, holding a pen, hovers a link and then Ctrl+clicks it
- **THEN** the hint says Ctrl and a click follow it, and the click turns to the link's page without drawing

#### Scenario: Hovering and pressing a link
- **WHEN** the user, holding the pointer, moves over a contents line that is a link and presses on it
- **THEN** a light yellow box shows over the line while the pointer is on it, darker while it is pressed
