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

### Requirement: The print sheet says how many sheets, and the size
Above the pages the sheet SHALL offer a size -- Fill the page (the default), Fit to page, Actual size -- and under the
page choices one line SHALL say how many sheets will come out ("2 pages will be printed"; for a range or the whole
notebook "4 pages will be printed in total"), kept up to date as the choices change. Fill SHALL cover the sheet with a
page of one tablet screen (its edges trimmed where the paper's shape differs) and run a longer page on at the sheet's
full width; Fit SHALL put each page on one sheet; Actual size SHALL print at the tablet's size (229 pixels an inch),
never wider than the sheet, a longer page running on. Every piece smaller than its sheet SHALL be centered on it.

#### Scenario: A long page, filled
- **WHEN** the user chooses Fill for a page written ten sheets long
- **THEN** the sheet says "10 pages will be printed", and the last, shorter piece is centered on its sheet
