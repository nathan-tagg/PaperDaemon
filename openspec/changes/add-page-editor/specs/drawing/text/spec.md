# Spec Delta

## ADDED Requirements

### Requirement: Typed text in the window keeps the tablet's layout
Typed text drawn in the window SHALL use the tablet's faces from the user's desktop app when present,
and otherwise an openly licensed family chosen to match their advance widths. With either face it SHALL
keep the tablet's column widths, sizes, line spacing, bullets, numbers and checkboxes, and the window
SHALL say when it is drawing the substitute.

#### Scenario: A user without the desktop app
- **WHEN** a user with no reMarkable desktop app opens a page with typed text in the editor
- **THEN** the text is drawn in the substitute family, wrapped in the page's column, and the window notes
  that the tablet's own face is not installed
