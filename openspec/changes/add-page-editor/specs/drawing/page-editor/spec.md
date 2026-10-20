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
cursor in the page's text, and a click below the text SHALL put it at the end of the text. The
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

### Requirement: Typing starts below the ink
When the user starts typing with no caret and there are strokes in the text column on or below the line the text would
go on, the editor SHALL add empty paragraphs and start the text in the first paragraph below the lowest of those
strokes. A caret the user places (a click, the arrow keys) SHALL stay where it is put. Anything landing on the page
while the user types (a stroke the user draws, the daemon's ink, and whatever else comes to be placed on a page) SHALL
let the caret go, as Esc does, so the next key starts typing below the ink again. A stroke wins over typing: the caret
SHALL go as the pen goes down, and no key or paste SHALL reach the page until the pen lifts. Backspace or Delete with
no caret SHALL go back into the text at its end and act there, adding no line below the ink.

#### Scenario: A drawing below the text
- **WHEN** a page has a line of text and, well below it, a drawing, and the user starts typing
- **THEN** the text starts on the first paragraph below the drawing

#### Scenario: The daemon's ink lands while the user types
- **WHEN** the user is typing on an open page and a job writes strokes below the text
- **THEN** the strokes appear on the open page, the caret goes, and the next key starts typing below them

### Requirement: An open page takes in what the daemon writes
While a page is open in the editor, the editor SHALL take in what is written to the page's file from elsewhere (a job's
strokes and text, a request the job swept), keeping what the user did in the editor, and SHALL never write over it.

#### Scenario: A job answers an open page
- **WHEN** a job writes strokes to a page open in the editor and the user then draws and the editor saves
- **THEN** the page's file holds both the job's strokes and the user's

### Requirement: Erasing a zone
The eraser SHALL offer Zone beside Strokes and Passing: a loop drawn with it SHALL erase every point of the strokes on
the layer in hand that lies inside the loop, and only those. A stroke crossing the loop SHALL be cut where it crosses,
what lies outside staying as strokes of their own.

#### Scenario: A loop across a line
- **WHEN** the user draws a zone loop over the middle of a long line
- **THEN** the middle of the line is gone and its two ends stay, each cut at the loop

### Requirement: Shapes and fills with the pen in hand
With a pen in hand, Shift or Ctrl and clicks SHALL set corners, drawn when the keys are let go: two corners a line, more
a closed shape (as is clicking the first corner again; Esc drops them). Ctrl and Shift together SHALL put each edge on
the clock's hours, every 30 degrees. Alt and a click SHALL fill the area of one
color under the click, bounded by what the page shows and never past the view. They SHALL be ordinary strokes of the
pen in hand, a fill laid in overlapping rows joined into one stroke where they touch, so a highlighter's fill does not
darken where its rows meet. Typing SHALL never start from these keys.

#### Scenario: Filling a drawn ring
- **WHEN** the user draws a ring with the fineliner and Alt-clicks inside it
- **THEN** the inside of the ring is filled in fineliner, up to the ring

### Requirement: Typing needs no click
Opened in the viewer, the page editor SHALL take the keys at once, and a key pressed in the viewer outside a field
(after a press in its bar, say) SHALL reach the page as if pressed there.

#### Scenario: Typing on opening
- **WHEN** the user opens a notebook page in the false mirror and types
- **THEN** the text appears on the page without a click first

### Requirement: Right-click erases
A right-click or right-drag on the page SHALL erase, whatever tool is in hand, and leave that tool in hand: what it
passes over; with Shift whole strokes; with Ctrl and Shift a zone, the loop it draws.

#### Scenario: Erasing with the pen in hand
- **WHEN** the user, drawing with the fineliner, Shift-right-drags across a stroke
- **THEN** the stroke is gone and the fineliner is still in hand

### Requirement: A fill is the decomposer's
A fill SHALL be painted by the decomposer itself: the engine runs its ring planner in C (fastdecomp rf_fill) on the
area, and its rings (closed, at rising depths from the area's edge, the first fine and on the edge, each level wider and
deeper) SHALL each be a stroke of the pen in hand at the planner's width. Without the engine (the editor opened from its
file) or with one that has no fill there SHALL be no fill, and the page SHALL say which.

#### Scenario: Filling an ellipse
- **WHEN** the user Alt-clicks inside a drawn ellipse
- **THEN** it fills with rings that follow its edge inward, not rows

### Requirement: The page always scrolls
The page SHALL scroll down, in the editor and in the viewer alike, whether or not anything is written below: until the
view's top reaches the page's foot (or the lowest ink or text past it), or a screen down for a page shorter than the
screen. A thin bar on the page at its right edge SHALL show where the view is, in sight while the page moves and fading a
moment after it stops (and while hovered or dragged), and dragging it SHALL scroll. The middle button SHALL autoscroll
as a browser does: a press drops a mark (a dot with the ways the page can go: up and down at every zoom, across too
past 1x) and the page runs toward the pointer, faster the farther it is; pressed and let go it keeps on until the next
press, Esc or the wheel, and held and moved it ends when let go. The press that ends it does nothing else.

#### Scenario: An empty page
- **WHEN** the user scrolls down on an empty page
- **THEN** the view moves down until its top is at the page's foot

### Requirement: Shapes by number
With a pen in hand and no text being typed, the keys 1 to 6 SHALL choose what a click makes: 1 the pen's own strokes, 2
a circle, 3 a triangle, 4 a square, 5 a rectangle, 6 an arrow, the pointer showing the shape. The first click SHALL set
one corner or edge and the second the other (Shift putting it on the clock's hours from the first), a preview following
the pointer between them; the shape SHALL be one stroke of the pen in hand, and the keys SHALL go back to 1 after it. A
circle SHALL span the clicks as its diameter, a triangle be equilateral with its tip at the first click and the middle
of the side across at the second, a square have the clicks as its diagonal, a rectangle as upright opposite corners,
and an arrow run from the first click to its head at the second. Esc SHALL drop a shape begun and go back to 1.

#### Scenario: A circle
- **WHEN** the user presses 2 and clicks twice on the page
- **THEN** a circle spanning the two clicks is drawn in the pen in hand, and the next click draws with the pen again

### Requirement: The shortcuts sheet
A ? by the document's name in the viewer SHALL open, over the viewer, a sheet of every key and click the viewer and the
page editor answer to: a list per kind (moving around, pages, and where the editor is open drawing, shapes, erasing and
typing), each item's bullet the icon of what it does, then its keys in capitals, then the action and a line on it, in
the window's language. Esc or Close SHALL close the sheet and leave the viewer open.

#### Scenario: Opening the sheet over a notebook page
- **WHEN** the user presses ? by a False Mirror notebook's name
- **THEN** the sheet lists the viewer's and the editor's shortcuts, and Esc closes only the sheet

### Requirement: The page's pictures
The editor SHALL draw a page's pictures (captures, pasted images, the daemon's pictures) by their four corners, over the
template and under the ink and text, and SHALL keep them through every save, written back as the tablet stores them.

#### Scenario: Drawing on a page with a picture
- **WHEN** the user draws a stroke on a page that holds a turned picture
- **THEN** the stroke is saved and the picture stays, its corners as they were

### Requirement: Select and capture
One slot in the bar, right of the eraser, SHALL hold Select and Capture, its menu choosing between them. Select SHALL take
the strokes of the layer in hand that a drawn loop holds (most of their points inside), framed, to move by the frame's
inside, scale by its corners (strokes and their widths alike) and turn by the handle above it (Shift: on the clock's
hours), each change one undo step; while dragged the strokes SHALL be drawn as plain lines and changed only when let go.
Capture SHALL copy what the page shows inside a drawn loop, pixel for pixel, to the system clipboard as a picture; a click
on a picture SHALL select it, to move, scale and turn the same way. Delete or Backspace SHALL remove what is selected and
Esc let it go.

#### Scenario: Turning a selection
- **WHEN** the user selects a flat stroke and turns the frame's handle a quarter, with Shift
- **THEN** the stroke stands upright

### Requirement: The clipboard
Ctrl+C and Ctrl+X SHALL put selected strokes on the system clipboard both as strokes PaperDaemon reads back and as a
picture any program takes, and a selected picture as its image. With no text being typed, Ctrl+V SHALL put back, centered
under the pointer, strokes as strokes (selected) or an image (PNG, JPEG, SVG and the like) as a picture at one screen pixel
a pixel; Ctrl+Shift+V SHALL put an image down as strokes, decomposed at the same size.

#### Scenario: Copying strokes to another page
- **WHEN** the user selects strokes, presses Ctrl+C, opens another page and presses Ctrl+V
- **THEN** the same strokes land under the pointer, selected

### Requirement: Checkboxes take a click from any tool but a pen
A click on a checkbox with any tool but a pen in hand SHALL tick or untick it, the pointer showing a pointing hand over
it; a stroke of the eraser passing over a checkbox SHALL NOT tick it. The eraser SHALL have three sizes, as the pens do.

#### Scenario: Ticking with the eraser in hand
- **WHEN** the user, holding the eraser, clicks a checkbox and then drags the eraser across it
- **THEN** the click ticks it and the drag leaves it ticked

### Requirement: The editor keeps up
A text edit SHALL redraw only the band of the page it touched (from the first paragraph changed to the end of the text),
an eraser only the rows its erased strokes took, and a repaint SHALL copy the page as shown rather than draw it again;
each SHALL show exactly what a full redraw shows. The editor SHALL not read the page's file to compare it while the user
is at work, only after a pause and before each save.

#### Scenario: Holding Delete
- **WHEN** the user holds Delete on a page with text and ink
- **THEN** each key redraws only the text's band, as fast as the key repeats

### Requirement: A mouse draws with an inferred hand
A stroke drawn with a mouse SHALL take a pressure inferred from its speed (slow pressed hard, fast lightly, smoothed) and
the direction of travel as its angle; a stylus SHALL keep its own pressure. The fineliner, the highlighter and the
shader SHALL keep their width; the ballpoint, the pencils, the marker and the brush SHALL widen with pressure (the brush
most) and the pencils' shade follow it; the calligraphy pen SHALL be broad across its nib, held at 45 degrees, and fine
along it.

#### Scenario: The calligraphy pen
- **WHEN** the user draws with the calligraphy pen up to the right, then down to the right
- **THEN** the first stroke is thin and the second broad
