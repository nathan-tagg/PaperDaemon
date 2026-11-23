## ADDED Requirements

### Requirement: Printing from the page editor
Ctrl+P in the page editor SHALL open a print sheet with the printers Windows has, its default chosen, and three
choices of pages -- this page, a range, the whole notebook -- each with its page numbers to the right of it, then
Cancel and Print. Pages SHALL be drawn as the tablet draws them and printed through Windows itself, no other program
driven. A screen of the tablet SHALL be a sheet, fitted to the paper; a page written past its first screen SHALL run
on over as many sheets as it has screens. Page numbers outside the notebook SHALL be refused before anything prints.

#### Scenario: Two pages of a notebook
- **WHEN** the user prints a range of two ordinary pages
- **THEN** two sheets come out, each a whole page as the tablet draws it

#### Scenario: A long page
- **WHEN** the user prints a page written eight screens long
- **THEN** it comes out on eight sheets, in order, nothing left out

#### Scenario: A page number past the end
- **WHEN** the user asks for page 99 of a notebook of 12
- **THEN** the sheet says which pages there are, and nothing prints
