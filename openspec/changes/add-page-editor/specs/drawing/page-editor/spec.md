# Spec Delta

## ADDED Requirements

### Requirement: The editor's page is page data
The page editor SHALL hold a page as the tablet's page data: its frame, its layers, and lines carrying
the pen, color, thickness scale, color RGBA, item id and, per point, x, y, speed, direction, width and
pressure. Every new line SHALL be stored as from a pen held upright at 50% pressure.

#### Scenario: A fineliner stroke
- **WHEN** the user draws with the fineliner at its large size
- **THEN** the page gains one line with the fineliner's pen, thickness scale 3, and every point stored
  with width 24 and pressure 128

### Requirement: The editor draws with PaperDaemon's renderer
The editor SHALL draw a page with PaperDaemon's own renderer, so what the user sees while drawing is
what PaperDaemon renders, and SHALL redraw a stroke while it is being drawn.

#### Scenario: A highlighter over ink
- **WHEN** the user highlights across a line of ink
- **THEN** the ink stays dark under the highlight, as PaperDaemon's renders draw it

### Requirement: Two pen pickers like the tablet's
The editor's bar SHALL hold, beside the pages grid, two pen pickers, the text tool and the eraser. A
picker SHALL show its pen's head and its color as a dot at its top right, and the tool in hand SHALL be
shown inverted. Choosing the tool already in hand SHALL open its menu: the pen's name, the nine pens in
a 3 x 3 grid, the sizes (except for the highlighter), and the pen's colors, each a dot over its name.
The highlighter SHALL offer six colors, the shader eight and every other pen nine.

#### Scenario: Changing the second picker to a red fineliner
- **WHEN** the user chooses the second picker, chooses it again, then the fineliner and red
- **THEN** the second picker shows the fineliner's head with a red dot, and its strokes are stored as a
  fineliner in red

#### Scenario: The highlighter's menu
- **WHEN** the user opens the menu of a picker holding the highlighter
- **THEN** it shows no sizes and six colors in two rows

### Requirement: The eraser erases strokes or what it passes over
The eraser SHALL offer two modes: erasing whole strokes, and erasing what it passes over by splitting
strokes where it crosses them. It SHALL sweep the whole path between two pointer samples.

#### Scenario: A fast pass across a thin stroke
- **WHEN** the user drags the eraser quickly across a fineliner line in the passing-over mode
- **THEN** the line is cut where the eraser crossed it and both ends remain

### Requirement: Typing on the page
Typing SHALL NOT need the text tool: with no cursor, a key that types SHALL put the cursor at the end of
the page's text, and the pen in hand SHALL keep drawing. With the text tool, a click SHALL place the
cursor in the page's text, and a click below the text SHALL add empty paragraphs down to that line. The
tool's menu SHALL set the column to narrow, medium or wide for the whole page. Styles, lists, bold,
italic, cut, copy and paste SHALL be keyboard actions, with no toolbar over selected text; Ctrl+Backspace
and Ctrl+Delete SHALL delete the word before and after the cursor, with or without Shift. Text and ink
SHALL be separate: deleting text SHALL NOT delete or move ink.

#### Scenario: Typing with a pen in hand
- **WHEN** the fineliner is in hand and the user types a word
- **THEN** the word is added at the end of the page's text, and the next stroke is drawn with the fineliner

#### Scenario: Deleting a word
- **WHEN** the cursor is after "two words " and the user presses Ctrl+Shift+Backspace
- **THEN** "words " is deleted and "two " remains

#### Scenario: A bullet from the keyboard
- **WHEN** the user types "- " at the start of a body paragraph
- **THEN** the paragraph becomes a bullet and the two characters are not kept

#### Scenario: Deleting the paragraph beside a drawing
- **WHEN** the user deletes the paragraphs a drawing stands beside
- **THEN** the text below moves up and the drawing stays where it was

### Requirement: Moving through text and many cursors
The cursor SHALL move with the arrows, Home and End; with Ctrl by word (left and right), by paragraph
(up and down) and to the text's ends (Home and End); with Shift they SHALL select. Ctrl+Alt+Up and
Ctrl+Alt+Down SHALL add a cursor on the line above or below, Ctrl+Alt+click SHALL add one where clicked,
and Alt+Up and Alt+Down SHALL move the cursors' paragraphs. Every key that moves, selects, types or
deletes SHALL act at each cursor. Copying SHALL take every selection, one per line; pasting as many
lines as there are cursors SHALL give each cursor its own line.

#### Scenario: Typing at three lines at once
- **WHEN** the cursor is at the start of the first of three paragraphs and the user presses Ctrl+Alt+Down
  twice and types "> "
- **THEN** each of the three paragraphs starts with "> "

#### Scenario: Pasting a line to each cursor
- **WHEN** three lines were copied and there are three cursors
- **THEN** pasting puts the first line at the first cursor, the second at the second and the third at
  the third

### Requirement: Layers
The bar SHALL hold a layers control listing, as the tablet does, the page's drawing layers top first,
then Text, then Template, then New layer. Text and Template SHALL only be shown or hidden, as the page's
root_document_visible and background_visible. The user SHALL choose the
layer the pens and the eraser work on, show or hide each layer, add a layer above the one in hand,
delete it, move it up or down, and collapse it into the layer below when there is one: its strokes are
made anew on top of that layer's, as the tablet makes them, and the layer is removed. Layers SHALL be painted bottom to top, hidden layers SHALL NOT be
drawn, and a hidden layer SHALL NOT take strokes or erasing. Every layer change SHALL be undoable.

#### Scenario: Hiding a layer
- **WHEN** the user hides Layer 2
- **THEN** its strokes disappear from the page, stay in the page data, and come back when it is shown

### Requirement: Choosing a template
The Template row's button SHALL open a screen in the dialog listing every template the user has, the
defaults and rM Methods together, with no tabs and no filter: a scrollable grid of each template's icon
over its name, the page's template underlined. Choosing one SHALL set the page's template.

#### Scenario: Picking a grid
- **WHEN** the user opens the Template row's button and chooses Grid medium
- **THEN** the page's template is Grid medium, drawn under the text and every layer

### Requirement: Drawing keeps up with the pen
A stroke being drawn SHALL be drawn one segment at a time over the page and SHALL redraw only the part of
the screen it touched, with the same result as drawing the finished stroke whole. The eraser SHALL
redraw the page only when it removed something.

#### Scenario: A long stroke on a full page
- **WHEN** the user draws a long stroke on a page of forty strokes
- **THEN** each pointer move costs well under a frame, and the finished page equals the page drawn whole

### Requirement: Undo, redo and zoom
The editor SHALL undo with Ctrl+Z and redo with Ctrl+Y or Ctrl+Shift+Z, for strokes, erasing and text
alike. Ctrl with the scroll wheel SHALL zoom from 0.5x to 5x around the pointer; the page SHALL always
open at 1x, showing what the Paper Pro shows at 1x; the zoom SHALL show at the top while it changes and
return to 1x when clicked.

#### Scenario: Undoing an erase
- **WHEN** the user erases across two strokes and presses Ctrl+Z
- **THEN** both strokes are whole again
