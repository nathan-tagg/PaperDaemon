## ADDED Requirements

### Requirement: A PDF's or a book's text can be selected and copied
With the text tool in hand on a page of a PDF or a book, a drag SHALL select the document's own text from the
character under the press to the character under the pointer, in reading order, and Ctrl+C SHALL copy the
selected text. Selecting SHALL write nothing to the page.

#### Scenario: Copying a sentence from a PDF
- **WHEN** the user, holding the text tool, drags across a sentence of a PDF page and presses Ctrl+C
- **THEN** that sentence's text is on the clipboard and the page is unchanged
