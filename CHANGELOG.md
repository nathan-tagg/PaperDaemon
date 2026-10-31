# Changelog

## 0.2.2

- 0.2.1's window showed nothing in its main area: a script of the Daemon panel would not load (a name declared twice). Fixed, and every script of the window is now checked before a release.

## 0.2.1

- The graphics card chosen in Settings is the only one PaperDaemon uses, or none: with the integrated card chosen, nothing of PaperDaemon's lands on the other card (the window drew on the card the screen hangs from as well). Choosing the processor uses no card at all. A change of card or processor restarts the window at once, on Settings.
- Choosing the integrated card could stop the editor with "Dispatch workgroup count X (65536)". Large passes are spread over rows of workgroups, as the card asks, and when a card cannot be used the notice says why in plain words.
- The working canvas is at most twice the tablet's resolution. Zoomed in past 2x, the page is drawn at two pixels a page unit and enlarged to the screen; a very wide window no longer draws more than twice the tablet's pixels.
- Scrolling slides the page on the card, as 0.2.0 meant it to: every scroll step drew the whole page again (and made a list of every stroke on it). On a 30,000-stroke page the integrated card's work for a scroll frame went from 8.6 ms to 1.3.
- Lifting the eraser after a long swipe: the pieces go into the page's order a few hundred at a time between frames (13 to 24 ms steps before, 2 to 3 ms now).
- Less graphics memory: the page's records grow by an eighth when they run out (they doubled), scrolling moves the page through a band 256 rows tall (it kept a second copy of the whole canvas), and each frame's culling looks only at the records in use.
- The page's points take less than half the graphics memory: on the card each point is one 32-bit word, its place to a 32nd of a tablet pixel and its width to a 16th, sixteen to a block that keeps their corner, their strokes and where each begins. A 30,000-stroke page's records went from 19 MB to 8 MB. Each block's box (which blocks an area or the eraser can reach) is kept in eight bytes, whole page units rounded outward (it was sixteen). What the engine draws for the tablet is unchanged, byte for byte.
- The page draws faster than in 0.2.0. On a 30,000-stroke page, on the integrated card: a whole-page redraw (a zoom step) 18.2 ms to 18.0, an erase frame 5.4 to 4.9, a pen frame 1.1 to 0.85, a scroll frame 8.6 to 1.3, and the page settles in about 130 ms after an erase is let go (178); the card writes the pieces a thread a point. On a discrete card: a redraw 1.25 ms to 0.98, an erase frame 0.79 to 0.52, a scroll frame 0.85 to 0.13. While nothing is being erased the strokes are drawn by shaders that carry only what they draw; an erase draws the strokes it has not reached the same way, and the full shaders only where it cut. The shrink from the working canvas to the screen, part of every frame, reads its tables in one go and sums each row in floats, exactly as before: 1.6 ms of each frame to 1.05.
- Pictures PaperDaemon puts on the tablet are made at twice the tablet's resolution, as charts already were: pictures and coloring pages, the games' pages (the chess board and its pieces, the chat, the talk strip, the adventure's pages and its journal, the cast book), PDF pages and PaperDaemon's logs. Their layout is as before.

## 0.2.0

- The page editor draws with WebGPU on the graphics card (Direct3D 12), and the engine draws the tablet's pages with the same shaders. A page is a handful of draws, in the page's order, kept on the card. Pens, highlighters, pencil grain and washes are decided pixel by pixel in the shaders, so a page looks the same however it was drawn: in place, whole, scrolled or reopened. The engine's pages are byte for byte what they were, and quicker (64 ms a page to 45 ms). WebGL2 is gone. On a card that only runs Direct3D 11, the editor draws on the processor.
- Nothing draws the whole page again for a change to part of it. Erasing, undo, redo and a selection being moved draw again only the pixels they changed. A selection is moved where it lies, on the card. Scrolling slides the picture by whole pixels and draws only the strip that came into view.
- Erasing happens on the graphics card. Each stroke the eraser cuts is drawn as what is left of it. Once the eraser has moved on, its pieces are made strokes of their own on the card, a few hundred a frame, so lifting the pen leaves little to do. On a page of 30,000 strokes, a fast swipe that cut 22,000 of them is done 124 ms after the pen lifts on a desktop graphics card and 130 ms on integrated graphics (328 ms and 327 ms before this release's last change), with the swipe's frames as light as before.
- Ctrl+Z pressed while a swipe was still being finished undid the step before it. Undo and redo now wait for the swipe.
- The page's file is put together, compared with the file on disk and written in a background thread. A save now takes under a millisecond of the editor's time on a page of 30,000 strokes (10 to 45 ms before).
- An edit costs what it changed, not the page. The page's end (how far it scrolls), undo and redo, letting go of a selection, the end of a swipe and the first key of typing no longer go over every stroke, and the typed text's layout is kept by a count of its edits instead of being written out and compared every frame.
- The bucket fill works on the graphics card.
- Settings, Renderer: GPU (the default) or CPU, and with GPU, which graphics card. The default is the Direct3D 12 card with the most memory.
- PDF and EPUB pages: with the text tool, the document's own text is selected with the cursor and copied, as the tablet's pen selects it.
- Mirror pages can be edited. Changes are written into the tablet's own file in place: strokes keep their ids, erased strokes are erased as the tablet erases them, and typed text is edited block by block. They are sent on Ctrl+S and when the document is closed, and a page the tablet changed meanwhile is not written over.
- When an erase falls behind the pointer on a slow machine, the path not yet erased shows as a 75% clear stroke over the ink until the erase catches up.
- After an undo brought strokes back, the next swipe could leave a square of page empty, and pieces of an undone erase could come back. Both fixed.

## 0.1.85

- Passing erase, made smooth on full pages and on slow machines. The pointer now only marks the eraser's path, and each frame does as much of the erasing as a sixtieth of a second has room for (sweeping the path, drawing again what changed, then making the pieces), leaving the rest to the next frame. The screen never stops: on a slow machine a very fast swipe trails the pointer and catches up as it slows. Measured on a page of 30,000 strokes flicked across end to end: at full speed every frame took under 11 ms and letting go 9.5 ms; with the processor slowed four times, 99 frames in 100 took under 21 ms, with 38 pauses over 16 ms where 0.1.84 had 280, and each pointer move cost 0.3 ms where it cost 14 ms.
- No stroke is made while the eraser moves. Each stroke it cuts is kept as what is left of it, and the graphics card draws it so in its place. The pieces are made in the frames' spare time and when the swipe ends, from what the card already drew.
- What a swipe changed is drawn again in cells of the page, each once however often it changed: where ink went first, then the grain or wash of the pieces it changes, which only change how they look.
- A swipe let go while it is still catching up finishes in the frames after. A key, a press, a paste or leaving the page finishes it first. What is drawn is the same pixel for pixel as a full redraw and as the same strokes loaded fresh, also after a swipe ended that way.
- A notebook opens on the page its cover names (Page 2 of 2), the page it was last open on. It opened on page 1.

## 0.1.84

- The page editor, made quick on full pages. Measured on a page of 30,000 strokes (a decomp, with hand strokes of every pen over it): a passing swipe's longest pause went from 31 ms to 7 ms, and the graphics card's work for it from 5.1 s to 0.9 s; letting go of a pen stroke from 35 ms to 3 ms; the longest pause while scrolling from 114 ms to 9 ms, and while zooming from 164 ms to 6 ms. What is drawn is the same, pixel for pixel: checked against a full redraw and against the same strokes loaded fresh, on the card and off it.
- Erasing: the eraser's path since the last move is swept at once, and each stroke is cut there once, exactly where it enters and leaves it (it was cut at every half radius of the path, and the pieces of everything cut were drawn over the page each frame, more of them every frame: the hitches). Only the area that changed is drawn again, the strokes changed in place among the page's, so what lies over what stays exact. Letting go of a swipe draws nothing again.
- A stroke being drawn goes onto the card where it will lie: nothing is copied off the card when it starts, and nothing is drawn again when it ends. Typing redraws only the rows of text it changed; a zone erase, a shape, a fill and a paste only their area.
- Nothing is read back from the graphics card while the page is idle: a copy of the whole page was made 0.4 s after every redraw, and a swipe or a stroke that began just then waited for it.
- Saves wait for the pen or the eraser to lift, and make only the new strokes' part of the file. A page's points are held once (the file as read kept a second copy of every point), scrolling no longer lays out the text or walks every stroke each step, and the eraser's index of the strokes is made while the page is idle and kept through every change.
- Without a graphics card, the page drawn again after an erase was the wrong rows of it: fixed.

## 0.1.83

- The keys change an erase mid-swipe, without a stop: Ctrl pressed or let go during a Shift-drag switches between erasing what it passes over and whole strokes, Alt added starts a zone right there, and Alt let go erases the zone and carries on. The pointer changes with the keys.
- Paste as strokes (Ctrl+Shift+V) comes out up to 1,600 wide whatever the picture's shape. The limit was on its longest side, so a picture a little taller than wide came out about 1,400 wide; the decomposer now gets a box the picture's own shape (up to 1,934 tall).
- Zoomed or scrolled sideways, subtle gray dotted lines mark where the window's edges fall at 1x: what the tablet shows across.

## 0.1.82

- Send to the tablet answers at once. The page is written and its sync started in the background, so the window never waits on the cloud; if there is nowhere for it to land, it says so at once.
- The passing eraser leaves a clean path. A piece it had already cut was never cut again (it kept its count of points, and was taken as untouched), so each stroke was cut only where the eraser first reached it, a stub left standing in the swipe. Strokes are now cut back to the eraser's full reach, measured to the edge of their widest ink, and crumbs left between the eraser's circles go with them.
- Erasing no longer hitches when a swipe pauses: the page is not read back from the graphics card while a swipe is under way, and an erase frame no longer lays the typed text out again.
- Ctrl+Shift+V pastes as strokes while typing too: with an image or copied strokes on the clipboard it lets the text go and puts them down as strokes (only text goes into the text). Strokes copied from a page come back as the strokes they are, not their picture decomposed.
- With Select (or Capture) in hand, the number keys shape the loop: 2 a circle, 3 a triangle, 4 a square, 5 a rectangle, for one drag, then a freehand loop again. No key starts typing while Select is in hand.

## 0.1.81

- Pages with the daemon's notes open on the tablet again. The tablet will not open a page holding an item of an author it does not know, and the notes were written under an author of their own (218): every page they reached became unreadable there. The notes are now written as the tablet's own author, numbered well clear of what the tablet adds meanwhile, and known as the daemon's by their layer and their machine-drawn strokes. Anything left under the old author is taken out of the page the next time a note is written, and the page opens again. Writing a hand puts on the Daemon layer is read as the user's.
- Decompose: saving a picture says only "Saved to Downloads", on a line every card keeps, so nothing in the row grows or moves.

## 0.1.80

- What a job writes is numbered as the tablet's own again (author 1). The author of its own that 0.1.79 gave it broke a page on the tablet: a page of strokes under it would not open.
- A page the tablet keeps a "not deleted" mark on ({value: 0}) is a live page: PaperDaemon counted every such mark as deleted and hid those pages. A page PaperDaemon deletes is stamped after the document's latest change.

## 0.1.79

- A page could stop opening on the tablet after a job wrote on it. Everything a job writes (its strokes, typed text and pictures) was numbered as the tablet's own items, after the highest number the page had when the job read it; whatever the user added on the tablet meanwhile got the same numbers, and the tablet cannot open a page with two items of one number. What PaperDaemon writes now has an author of its own, as the daemon's notes already did, so it can never share a number with the user's. (Pictures written under it also needed their author stored as one byte, as the file format has it.)
- Daemon > Notes lists each library's notebooks with the one that had a job most recently first.
- Deleting a notebook (on the tablet or in the False Mirror) deletes its notes.

## 0.1.78

- After an update, the window could show every label by its name ("np.label") until PaperDaemon was opened again: it read its words once, as it opened, and when that was before the engine answered it never read them again. It now reloads itself a moment later until the words are in.

## 0.1.77

- Esc on a page closes the notebook, as it does from the viewer's bar. The page lets go of what it has first, one Esc each: a menu, the caret, a selection, a shape or corners being set, the template picker. In the page grid, Esc still steps back to the page first.

## 0.1.76

- Daemon > Notes shows the False Mirror's notebooks too, under their own heading. Their notes are kept by the False Mirror's own engine, and the panel only ever asked the tablet's.
- Ctrl+W closes the open notebook; Ctrl+Tab and Ctrl+Shift+Tab go to the next and the previous one in its folder. They work from the page too, and are on the shortcuts sheet.
- Deleting in the False Mirror asks only "Delete ...?", without the line about the trash.
- Written replies are the size of the typed text: lettering at 26 (it was 32; a one-line title 30, was 38), its lines at the typed lines' own pitch, so the user's lines and the reply's read as one column.
- A reply starts closer to what is above it: under typed text, after the typed text's own space between paragraphs (25); under ink or a picture, 40. It was 80 under anything.
- The daemon's notes keep to one layer. The record of each page's layer could be lost when two notes were written at once (one of them read the file while the other replaced it, took it for empty, and wrote over every other page's record); a page that lost its record got a second Daemon layer, and notes could end up on a layer the tablet no longer showed. The record is now kept safely, the layer is always found on the page itself, and a page that already has two takes the empty one out.

## 0.1.75

False Mirror:
- No more Done buttons. Esc lets a selection go, in the library and in the page grid.
- Esc in the page grid steps back one thing at a time: the page chosen to move next to, the move, the pages chosen, and then out of the grid to the page. The viewer closes only from the page.
- Move is no longer a sheet. In the library, the bar turns into "Move ...: open a folder"; open folders as usual, and in any folder the items are not already in, the bar offers Move here.
- Moving pages: the bar asks for the page they go next to; choose one in the grid and the bar offers Move before and Move after, each with its icon. Move out leaves the notebook: open another notebook in the library, choose a page in its grid, then before or after.

Page editor:
- Back and forward (the mouse's buttons, Alt+Left and Alt+Right, the same thing) walk the history of pages you have been on, wherever the keys or the pointer are, the page open to edit or to look at. At either end they do nothing: they never close the viewer or move the app behind it.
- The caret is as tall as the letters, not the whole line, and leans while italic is on.
- With the eraser in hand, Shift changes nothing: its own pointer and its own erase. The erasers' pointers are made ahead, so the system's large cross no longer flashes before the circle.
- Templates PaperDaemon draws itself (the hexagons and calligraphy pages) say why on hover, in the editor's picker and in New notebook.

The lineup:
- The model reads the user's bold and italic in the typed text (as **bold** and *italic*); in a roleplay italic is often an action.

## 0.1.74

The page editor:
- A template covers all that can be drawn on. What repeats in it (the grids, dots, isometric, the hexagons, lined and margin pages) runs on across the whole drawable area and down as far as the page goes; what does not (planners, music, storyboards, perspective) stays on the page.
- Fills: the ballpoint, fineliner and calligraphy pen fill their area instead of spilling far past it. The other pens fill as before.
- Alt + drag fills each new area of the same color the drag passes over, read from the page as it was before the drag, so nothing is filled twice; it counts as a drag only once the pointer has really moved.
- Ctrl + A with a pen in hand selects every stroke on the layer; Ctrl + Shift + A those of the pen's kind; Ctrl + Shift + Alt + A those of its kind and color. In text it selects all the text, as before.
- A click on a thin line (a template's hexagons, a fine stroke) fills the line at any zoom, not only zoomed in.
- The erasers' pointers are drawn smooth at the screen's own pixels, and show the moment Shift goes down (while typing, once the mouse moves or the typing stops).
- Scrolling the caret out of sight lets the text go, so 1 to 6 choose shapes again instead of typing.
- An eraser's ring no longer stays on the page after a swipe let go off it.

## 0.1.73

- A PDF page far taller than it is wide (a long scroll of a page) is shown at the page's width and scrolls, in the Mirror, the page editor and the page pictures. Since 0.1.69 the whole of it was squeezed onto one screen.
- The mouse's back and forward buttons over a page turn the viewer's pages, as Alt+Left and Alt+Right do. Over the page they used to take the app's window back a screen, behind the viewer.
- The ? on a page of the Mirror (which only looks) lists only what works there: moving around and turning pages, not drawing, erasing and typing.

## 0.1.72

- The page editor's right-click menu is the only one: the window's own menu (Back, Refresh, Inspect) no longer opens over it.

## 0.1.71

The page editor's mouse and keys, reworked:
- A mouse click that does not move draws nothing: no more stray dots. A drag draws; a pen's tap still makes a dot.
- Erasing is on the keys, with the left button, whatever is in hand: Shift + drag erases what it passes over, Ctrl + Shift + drag whole strokes, Ctrl + Shift + Alt + drag a zone. With the zone's keys held (or the zone eraser in hand), 2, 3, 4 and 5 make the zone a circle, triangle, square or rectangle, dragged out. The pointer becomes the eraser itself, as wide as its size in the eraser menu: an empty circle, the circle crossed through, or the zone dotted. Typing capitals with Shift does not flicker it.
- The right button opens a menu for what is under it: on a selection Cut, Copy, Delete and Duplicate; on the text Cut, Copy, Paste, Paste matching formatting, Paste as strokes and Select all; on the paper Paste, Paste as strokes and Select all.
- Typing with a pen in hand: over the text the pointer is the I-beam and a click puts the caret there (a drag selects); off the text the pen draws. Shift + click extends the selection. The text tool's icon is the I-beam.
- Snap to angle, every 15 degrees (the 30s and the 45s), is Alt: a shape's second point, Ctrl + Alt + click for corners, and turning a selection. Corners are Ctrl + click. A shape (2-6) can be dragged out, or set with a click and then a second press, ended where it is let go.
- Paste keeps bold and italic; Ctrl + Shift + V pastes in the caret's formatting.
- The shortcuts sheet (the ?) shows all of this, in every language.

## 0.1.70

Measured on the tablet's own pixels (its screen share of a calibration notebook, 2026-10-22):
- Pen lines are as wide as the tablet draws them: a pen's width is its width field / 4 (fineliner, ballpoint and calligraphy exactly; marker, paintbrush and the pencils by their own measured factors), whatever its thickness setting. They were drawn at 0.58 of that. What PaperDaemon writes to the tablet is unchanged.
- Colors are the tablet's: pure pen colors (blue 0,0,255, red 255,0,0, and so on), highlighters in the pens' colors (blue is blue, gray is 148), a shader without a stored color black or gray as the tablet draws it, and a marker in the gray-overlap and highlight colors black.
- Pencil and mechanical pencil look like the tablet's: the grain is single pixels fixed to the paper, the same pixels under every stroke, as even across a stroke as along it, and as dense as the tablet's at every pressure; no pencil line narrower than 2 units.

## 0.1.69

- A page of a PDF or a book fills the screen as the tablet shows it (its zoom, "best fit": the whole page, as large as fits). Its frame is its own size -- a cover 1245 units wide, a planner 5095 -- and shown on a notebook's 1620 it sat small in a white margin, or showed only its top corner. Covers fill the page now, in the Mirror, the page grid and the covers.
- A short, wide page (a hymn's last lines, a landscape sheet) is no longer drawn as a narrow white strip.
- Pictures show on the pages of a document in the trash.
- A page that names one item twice (a group and a stroke under one id, as an older writer left some pages) opens in the Mirror and the page editor, drawn whole, instead of failing to open.

## 0.1.68

- The page editor and the Mirror draw a drawing where the tablet does. A group of strokes anchored to the typed text (below it, or at a paragraph) was drawn at its stored coordinates, top left and over the text, and the grid's pictures and covers with it; a save from the editor wrote it there.
- A picture has one size: the page's full width (half when the plan asks for it small), as tall as its picture, centered, under the reply's words. It used to be a share of whatever room was left, so the same request gave a big picture on an empty page and a small one lower down. It is never shrunk to fit; the page extends below.

## 0.1.67

- What a job writes is remembered as its own again. Since 0.1.15 the host recorded its ink only when a job ran onto a new page, so the next job read everything it had written before as yours: its own answers as requests, and a picture's thousands of strokes as your handwriting.
- Reading a page no longer stalls on a big drawing. Looking for arrows compared every pair of stroke ends; a picture of 13,000 strokes took 96 seconds with the graphics card idle. It now takes a fraction of a second, with the same result.
- False Mirror: the page grid's selection bar no longer stays over the viewer's bar. Done always gives the bar back, and closing the notebook lets the chosen pages go.

## 0.1.66

- Daemon notes are ONE message, one line, rewritten each time: when he saw the job, what it is doing now, and how it ended (finished, failed or skipped). They never wrap; a note too long for its line is cut.
- False Mirror: the page editor no longer copies the daemon's layer as your own. It saved his notes under your ids, so he could not erase them and made himself a new layer every time: notes piled on top of each other and Daemon layers multiplied. The editor now shows his layer, never draws on it, and keeps it as he wrote it.
- A job with a picture no longer crashes after the picture lands ("float32 is not JSON serializable"). The picture's box was measured from its traced strokes, whose numbers are numpy's, and went back to the model as JSON.
- New notebook: every template's icon is the same size and color (rM Methods' icons were bigger and gray), and the list scrolls without a scrollbar, fading out where there are more. The tags field is gone for now. The page editor's template picker draws the same icons.
- The selection bars say "Tag", and the tag dialog is titled by the notebook's name.
- Daemon notes: the devil stands clear of the signature, and a line leaves exactly the signature's room. The traced signature is optional content (`content\signaturem_sig_daemon.json`); without it the name is lettered.

## 0.1.65

- False Mirror: select several notebooks and folders at once. A long press or a right-click selects, and while anything is selected a click adds an item or takes it away (Esc, or a click on nothing, lets them all go). Their actions take the place of the library's title bar, as the tablet's action bar does, so nothing is covered and nothing moves: Export, Duplicate, Move, Tags, Delete, Done.
- False Mirror: pages in the grid are selected the same way, and their actions take the place of the viewer's bar the same way: Select all, Duplicate (each copy right after its page), Move (before or after a page of this notebook or another, or to its end), Tags, and Delete (for good, after you confirm, as on the tablet).
- False Mirror: New notebook takes tags.
- False Mirror: its notebooks get Daemon notes too, on the Daemon layer, where the page editor shows them. The host still never sees them.
- The setting is called "Daemon notes" again.
- The page's tag button says "Add" again (it had become "New", the + menu's word).

## 0.1.64

- False Mirror: a page no longer goes back to the host after every answer. The daemon there sees a page as at your last sync (closing it, or Ctrl+S), and a page it had just answered still looked, in that older view, like it had changed since the answer. So the host answered again, its own answer this time, over and over. A job's own writing now counts as synced; what you change after it still waits for your sync.

## 0.1.63

- A page no longer answers itself over and over. Since 0.1.61 the daemon took the host's note that it had checked the page for its record, and wrapped the job up a moment before the host wrote it: the host's own answer was then seen as a change, and the page went back to the host again and again.

## 0.1.62

- A job's working bar and the window's spinners move even with Windows' "Show animations" off. The window took that setting as "reduce motion" and stopped them, so the bar looked stuck.
- A page is never queued twice when the daemon hands it over after a job that did not finish.

## 0.1.61

- Page editor: the eraser's circle stays under the pointer when the view scrolls (the wheel, or typing that takes the view down). It used to run away from it.
- The daemon no longer stops working when a page changes while a job works on it. The host recorded the job and the page was opened again for the change before the daemon looked, and the daemon then waited for good: no job ran, and no working bar showed.

## 0.1.60

- A picture a job makes after writing a reply goes right below the reply. The page's places are planned before anything is written, and laying out what is still to come below what really landed had stopped running: it shared its name with another function, and that one took its place. So a picture after a short reply went half a page down.
- Page editor: typing past the bottom of the view (or the arrow keys) scrolls the view to where you are typing.
- False Mirror: the bar on the cover of the page a job is working on moves smoothly. Each update used to draw it anew, starting its animation over every second, and the whole library was redrawn every five seconds.
- False Mirror: New notebook's templates are drawn as the page editor draws them, and its name field starts empty, "Notebook" its placeholder. New folder does the same.
- Tags have no case: "Joi" and "joi" are one tag in the page's tag menu and in a notebook's tags, and adding one keeps the spelling already in use.
- A job a host stopped in the middle of no longer leaves a working bar on its notebook's cover: the host clears it when it starts.

## 0.1.59

- Draw pages on the processor is a setting in Settings now, one for every lineup, under Network access. It was on each lineup's Text tab. A lineup that had it on turns it on for all.
- A folder PaperDaemon opens for you (a lineup's LoRA folder, the harnesses folder) opens in front, over PaperDaemon's window. It used to open behind every other app. The LoRA folder link no longer sends the window to another screen.

## 0.1.57

- Every lineup has a LoRA folder of its own. The LoRA folder link under the image model's start script opens it. Every LoRA put in it goes with every picture that lineup makes, with no harness to write: the image harness says how they are applied. PaperDaemon's FLUX.2 Klein and Z-Image Turbo harnesses send them in the request, the way stable-diffusion.cpp's server takes them. Nothing is merged into the model: take a file out and the next picture is made without it.
- The start script is told where the folder is, in %PAPERDAEMON_LORAS%. For stable-diffusion.cpp's server, load LoRAs with --lora-model-dir "%PAPERDAEMON_LORAS%". A LoRA the server does not list is left out of the picture, and the job's log names it.

## 0.1.56

- False Mirror: the + menu's Quick sheets is now Quick sheet.

## 0.1.55

- Send to Tablet works again with a kept decomp. It stopped with "too many values to unpack (expected 4)": the decomp's colors already carried their alpha, and the page writer added another.
- The inbox is now a tag, set in Settings beside the ignore and standing instructions tags ("inbox" unless you rename it). Send to Tablet adds its page to every notebook with that tag, in the Mirror and the False Mirror alike. A library with no tagged notebook gets the page at the end of its Quick sheets. A notebook with the inbox tag is never worked on. The two inbox settings are gone: tag the notebook you used as an inbox.
- After a send, its button says "Sent to all inboxes" until PaperDaemon is opened again, instead of a page number. Send logs goes to the same inboxes.
- False Mirror: the button at the top right is a +, and it has Quick sheets. That opens your Quick sheets on a new page, as the tablet's button does, and makes one if there is none.
- False Mirror: New notebook asks for the cover, as the tablet does (the page last visited, or the first page), and, with a reMarkable account signed in, a template. The name field no longer runs past the edge of the dialog.
- Messages and the text adventure: the page's picture ends where your space to answer begins, so you can type your answer there as well as write it. The tablet puts typed text under a picture, and the picture used to cover the whole page. The instruction sits at the picture's foot, lined up with where typed text starts. A turn reads what you typed and what you wrote, and takes both off the page.

## 0.1.54

- Messages: your reply is read wherever you wrote it on the chat page, not only inside the Message box. A reply written above the box was left unread, and the turn said nothing was written. The model now gets your handwriting alone, cropped close, without the chat picture or typed text around it, and all of it comes off once it is your bubble.

## 0.1.53

- Handwriting is read where it is. The picture the host reads is the whole page plus anything past its frame, and the words it found were placed as if the picture were the frame squeezed. On any page written past its foot, words landed on the wrong marks or on none. They are now placed from the picture's own corner.
- Notes on the page: the daemon writes "On it" the moment he hands a job over. After that, every time the host does something a note reaches the tablet: what it read on the page, its plan, each step as it ends (done or failed), and how the job ended.
- Notes on the page: the notes no longer pile up. Each note went up as a copy of the page with ids another note had used, and the tablet merged them into each other. Everything the daemon writes now carries his own author id, every note erases everything of his first, including notes in copies the page never saw, and his old notes are erased with them.
- Notes on the page: his layer is called "Daemon" by default, and the name is a setting, shown while notes are on. The renderer never reads his notes, and never reads a layer with that name that you made yourself. Only the page editor shows them. Your own writing on his layer is still read and never erased: the tablet writes on whatever layer is current, and it had put your writing there. His layer now goes at the bottom of the list of layers.
- Notes on the page: a tick in the retry box is found on a page with typed text. The tablet keeps the tick in a group tied to the text, stored far from where it is drawn, and the box was looked for in the wrong place.

## 0.1.52

- New setting, Retries (default 0): a job that failed is tried again on its own, up to that many times. A page with nothing to do is not a failure and is never tried again. A game turn that stops on an error now counts as a failure.
- New setting, Notes on the page (default off): the daemon writes on the page as he works, small, across the very top under the tablet's toolbar, on a layer of his own called PaperDaemon. The notes say the job was received, then the work at hand once there is a plan, then how it ended and how long it took, signed. A job that was skipped or failed gets a box: tick it and it is tried again. The notes are never read as your writing, never start a job, and are erased before the page goes to the host. The first two notes go up as copies of the page, so the page in the Mirror is never touched while a job runs.

## 0.1.51

- 0.1.50 was built with files from the build machine's own content folder inside it. A character pack installed in your content folder was then ignored, and characters could not be found. 0.1.51 is built without any of it, and the build now refuses to run if such files could reach the app.

## 0.1.50

- Messages: a reply with an empty picture line no longer sends a picture. The line after it was read as what the picture shows, and a picture nobody asked for was drawn.
- Messages: residents send a picture now and then, the way people text a photo (where they are, what they're up to, what they're talking about), and it goes with what they said. Most messages still have none.

## 0.1.49

- Messages: a group chat holds everyone you ask for. "The whole cast" was cut to eight people.
- Messages: a group chat's header is laid out like a real messaging app's. A few faces overlap with a "+N" for the rest, a big group is titled "N people" with the names that fit and how many more, and nothing runs off the page.
- Messages: in a group, everyone your message names may answer, plus a few others who would chime in: four replies at most unless you name more people. A big group no longer makes half its members answer every turn.

## 0.1.48

- Page editor: erasing with the right button while strokes are selected no longer leaves the selection's picture of them on the page until you click away. An erase now lets go of the selection first, so you see what it erased.

## 0.1.47

- Every picture of a page is drawn on the graphics card, by the same shaders as the page editor, through PaperDaemon's own build of ANGLE (Direct3D 11). The processor's renderer is the fallback. The card's memory is given back when a job ends, when the daemon is paused and when a decompose finishes.
- New lineup option, "Draw pages on the processor" (Text / Reasoning tab): that lineup's jobs draw their pages without the graphics card, leaving all of its memory to your AI server. The ? explains the tradeoff.
- If pages can't be drawn on the graphics card, the Daemon page says so, once a session.
- A large page opens much faster: its typed text is read without reading every stroke again.
- Reading pages is faster throughout: strokes, typed text and the page's fingerprint are read in C.
- The pictures the engine makes always hold the whole page and anything past its edges. Where the model points on a page with ink outside it now lands in the right place, and the games read the player's box from the same pictures.
- Mirror pages open in the page editor, read-only: no tools, nothing written, a PDF's or book's links work, and the arrow keys turn pages. The old picture viewer is gone.
- Mirror PDFs saved in the tablet's older layout open again.
- Page editor: draws at your screen's resolution, more as you zoom in (up to twice each way), and never coarser than the tablet's, averaged down to the screen. It uses less of the graphics card's memory.
- Thumbnails in the pages grid and on covers are drawn by the page editor on the graphics card, one at a time, only when one is missing, and again when that page or notebook is opened.
- A page that passes 250,000 strokes shows a warning in the page editor, once per page.

## 0.1.46

- Page editor: fixed the eraser freezing and then crashing the app. When the eraser only grazed a stroke, a Passing erase replaced the stroke with an identical copy, over and over, until memory ran out. A graze now takes nothing, and the pieces an erase leaves can no longer feed the same pass.
- Page editor: during a swipe, the pieces an erase leaves are added to the graphics card a frame's worth at a time and freed when the swipe ends, instead of being rebuilt every frame.
- Page editor: saves no longer fail with "access is denied" while you drag a large decomp. Saves of a page now run one at a time, and two saves never share a temporary file.
- Page editor: save status no longer shows over the page. The ? by the document's name turns into a spinner while a save is slow and into ! when one fails (the reason on hover). The ? is smaller.

## 0.1.45

- Page editor: erasing no longer rebuilds the page during a swipe. An erased stroke is blanked in place on the graphics card, and the pieces a Passing erase leaves are drawn on top; the page is rebuilt once, after the swipe.
- Page editor: the zone eraser works on loops with many strokes and on loops drawn round and round (every turn counts as inside).
- Page editor: a pasted picture (Ctrl+V) lands by the same rules as a decomp: at most 1,600 across, centered on the pointer, kept inside the view, and never above the top of the page. A decomp too tall for the view no longer goes off the top of the page.
- Page editor: when a page can't be saved, the editor says why.

## 0.1.44

- A page opens much faster: the engine reads its strokes in one pass in C (a 26,000-stroke page in 0.14 s, was 0.7)
  and writes them in one piece.
- Erasing on a big page: the eraser looks only at the strokes near it, the page is made again at most once a frame,
  and cutting a stroke skips what the eraser does not touch (passing erase much faster, stroke erase steady).
- Until the page has loaded, a spinner covers it and no stroke, key or paste reaches it.
- Typing starts below the ink's painted edge, so new text no longer lands on a decomp's wide washes.
- Passing is first in the eraser's menu.

## 0.1.43

- Zoom (Ctrl + scroll, Ctrl + = / -, Ctrl + 0) is the window's own: the page lays itself out again for the smaller room,
  as a browser's zoom does, so nothing runs off the bottom or is cut off at the side. It is still remembered.

## 0.1.42

- The page editor stays quick on a page holding a huge decomp: a redraw, a pan or a zoom never saves (only an edit
  does), the page is read again only when its file changed, and erasing or selecting no longer redraws the whole page
  or resends its every stroke to the graphics card.
- A page opens and saves several times faster: its strokes are read and written in bulk, and the editor and the engine
  pass it in a compact binary form, a quarter of its size as text (a 26,000-stroke page reads in 0.7 s, was 5).
- Washes are painted a third of a pixel past their exact edge, as the tablet does, so decomps show nearly no pinholes.
- Decomps are kept on disk, each with its strokes and its preview at the tablet's size, not in memory. They stay
  until deleted, and the Decompose screen pages through them (10, 50 or 100 a page). Save sits beside Delete.
- A pasted decomp lands under the pointer, moved in to fit the view, or centered when larger than the view; no stray
  "Decomposing…" or "…" text.
- The False Mirror's decompose inbox is in its own settings, labeled Decompose inbox.
- Start and Pause are one word each and stay on one line with the version.
- The False Mirror's setting fades in also when Windows' animation effects are off.

## 0.1.41

- The page editor draws on the graphics card (WebGL2): a pan, a zoom or an edit redraws a page holding a 24,000-stroke
  decomp in about a millisecond, where it took about a quarter of a second. Without WebGL2 it draws as before.
- A selection that moves floats: dragging, turning or resizing a decomp places one picture of it, and it is drawn into
  the page once, when let go. A pasted decomp lands floating, and a save writes the page once.
- The pens draw as the tablet does, measured on test pages: the pencils in grain that fills in with pressure, the
  paintbrush leaving nothing when very light and breaking up when fast, the ballpoint thinner and broken when light,
  and the calligraphy pen, the pencils and the shader at the tablet's widths.
- A mouse presses as a hand does, read off real strokes: hard nearly the whole way, landing a little lighter. Shapes and
  fills are drawn at that pressure, and pasted decomps at the decomposer's own.
- The five templates the reMarkable app draws in its own code (the hexagons and the calligraphy guides) are drawn by
  PaperDaemon, marked as approximations. Without a login, the Templates button says why there are none.
- Decompose: Send works with only the False Mirror's inbox, and needs a login only for the tablet's; when both take a
  page, it reports the tablet's page. Each decomp has Save (its picture into Downloads), the drop zone has paste, and
  the width goes to 1,600.
- The rail's foot stays in the window when it is zoomed in. The page arrows are the same buttons as the rest of the
  bar, and the page count stays on one line.
- A drag that starts on a link, a picture or selected text selects instead of showing a crossed-out cursor.
- The social sites setting is gone: a request for posts searches every site. The note about the editor's faces is gone.
- The zone eraser's menu has no sizes. The start script help says PaperDaemon may use up to 200 MB of the card's memory.

## 0.1.40

- A mouse draws with an inferred hand: pressure from its speed, smoothed, and its direction as the angle. The ballpoint,
  the pencils, the marker and the paintbrush widen when drawn slowly; the calligraphy pen is thin up to the right and
  broad down to the right. A stylus keeps its own pressure.

## 0.1.39

- A held key no longer stutters: a text edit redraws only the band it touched (about five times faster), erasing only
  the rows it took, and a repaint copies the page rather than drawing it again. The page's file is compared for the
  daemon's writes only after a pause, and always before a save.
- A checkbox ticks with a click from any tool but a pen, under a pointing hand; an eraser passing over it leaves it be.
- The eraser has three sizes; the one it had is the medium.
- A click below the text with the text tool goes to the end of the text, no lines added.

## 0.1.38

- Start and Pause are in the rail's foot, left of the version, on every screen.
- The Select and Capture menu is as wide as its two choices.
- The viewer widens to fit its bar when the window has room, instead of scrolling.
- New page is a button with a page and a plus.
- Ctrl+Shift+V reads the image off the clipboard (the browser had pasted it as plain text, the image dropped), and the
  page shows where the strokes will land while the image is decomposed.
- The page editor's frame may use the clipboard, so Capture and Copy reach it in the app.
- Text boxes and areas show no highlight ring when focused.
- [] and a space makes a checkbox, as [ ] does; [X] a ticked one, as [x] does.
- Esc closes an open menu first (the tags, a pen's, the eraser's, the layers', Select's), and only then the document.

## 0.1.37

- The page editor shows a page's pictures, turned ones too, and keeps them through every save.
- Select and Capture share a slot right of the eraser. Select takes strokes in a loop, to move, resize and turn (Shift:
  on the clock's hours) by its frame and the handle above it. Capture copies what a loop holds, pixel for pixel, to the
  clipboard, and a click selects a picture.
- Ctrl+C and Ctrl+X put strokes on the Windows clipboard as strokes and as a picture; Ctrl+V puts strokes back as strokes
  and an image as a picture, under the pointer; Ctrl+Shift+V puts an image down as strokes, decomposed at its size.
- Shapes by number: 2 circle, 3 triangle, 4 square, 5 rectangle, 6 arrow, by two clicks; 1 is the pen.
- Shift or Ctrl and clicks set corners (a line, or a closed shape); Ctrl+Shift puts the edges on the clock's hours.
- Alt+click fills an area with the pen in hand, as the decomposer fills a zone.
- Right-click erases what it passes over; with Shift whole strokes; with Ctrl+Shift a zone. The eraser has a Zone mode.
- A stroke wins over typing; typing starts below the ink; anything landing on the page lets the text go; Backspace with
  no cursor goes back into the text.
- An open page takes in what a job writes to it.
- The page always scrolls, with a bar that fades; the middle button autoscrolls; the zoom pill keeps the view's place.
- The viewer is the tablet's screen, 3:4, as large as the window allows.
- A ? by a document's name opens every shortcut, each with its icon.
- Start shows as paused while no lineup could take a page.
- A lone stroke is saved on its own.

## 0.1.36

- Typing starts below the lowest ink on the page, unless the cursor was put somewhere else.
- A stroke wins over typing: the text cursor goes as the pen goes down, and the keyboard waits until the pen lifts.
- Anything landing on an open page lets the text cursor go, as Esc does; the next key starts below the ink.
- An open page takes in what a job writes to it, and the editor no longer saves over a job's strokes.

## 0.1.35

- The notebook viewer's bar is laid out as the tablet's toolbar: the page editor's pens, text, eraser and layers on the
  left, the tag button, the page grid and the page arrows on the right; in the page grid, the chapters, the grid and
  Go to page. The tag button lists the tags used before as pills, and a field to add one.
- A page opens at its top as the tablet shows it, in the tablet's screen, and the page zoom stays centered.
- Pages of PDFs and books can be drawn on (not typed on), as on the tablet.
- The queue shows each job's handle, the tag that sent it, and its cross at the right.
- Typing starts below the ink when the line it would go on runs over strokes.
- Ctrl+S, or closing a document, syncs: only then are its changes a job.

## 0.1.34

- The notebook viewer is the same size at every zoom of the window: it no longer runs off the top and bottom when the
  window is zoomed in, or shrinks when it is zoomed out. Only its controls and words follow the window's zoom.
- A page shows as the Paper Pro shows it: its screen's shape, at 1x what the tablet shows at 1x, the tablet's gray past
  the paper. A page longer than the screen runs down to the viewer's foot, then scrolls.
- Ctrl + scroll over the viewer zooms the page, from 0.5x to 5x around the pointer, not the window; the zoom shows at
  the top while it changes, and clicking it goes back to 1x. Shift + scroll moves across a zoomed page.

## 0.1.33

- PaperDaemon reads books itself, laid out as the tablet lays them out: the same pages, lines and pictures, the faces a
  book carries kept for the books after it. A book the tablet has not sent its pages of yet shows its text instead of
  blank paper, and its chapters land on the right pages. The tablet's own pages of a book arriving never start a job.
- Imported books no longer need Microsoft Edge: nothing outside PaperDaemon lays them out.
- Without a reMarkable account, typed text and books are set in PaperDaemon's own faces, and templates wait for an
  account; signing in says first that typed text may shift slightly. The page editor loads its faces from PaperDaemon,
  never from the internet.
- Imported books can be converted by the tablet itself: a setting sends each one, for a moment, to the tablet's
  library, brings its pages back, and removes it there.

## 0.1.32

- Imports take EPUBs as well as PDFs, and are easy: Import opens the file chooser at once (several files at a time), or
  drop the files on the screen. Each is named by its file and lands in the folder that is open. A book is filed as the
  tablet files one, its pages laid out at the Paper Pro's size.
- The tablet's page templates, read from the reMarkable desktop app on this computer (never shipped): a page can be
  given one, chosen from all of them as the tablet's picker shows them, and it is drawn under the page.
- The rM Methods templates in the library are kept in the Mirror with their drawings.

## 0.1.31

- Something waits at the bottom of Settings, for whoever waits there long enough.
- The Tablet tab is now Mirror. Every tablet on an account shares one library, so its settings (temperatures, times,
  weeks, the decompose inbox, the location, the ignore and standing instructions tags) are in Settings, one set for
  all of them; the gear is gone.
- The Daemon screen has three tabs: Queue, Notes and Terminal. Drag a waiting job to reorder the queue; the cross
  takes a waiting job out, or stops the job being worked at once and leaves its page as it was.
- Notes are the notebooks' notepads, tidied: search, entries or plain text, Copy text.
- A tagged folder shows a tag on its icon, and the path shows each folder's tags.
- Pages keep their own tablet's frame: a page made on a reMarkable 2, Paper Pure or Paper Pro Move is laid out,
  answered and previewed in that frame.
- Everything PaperDaemon writes reaches the tablet one way, through the same push: game journals and the decompose
  inbox included.
- A text server that answered compressed no longer shows as "HTTP 400" with garbage after it.

## 0.1.30

- What becomes a job: after PaperDaemon's first look at a complete mirror, every new or changed tagged page is a
  job, whether PaperDaemon was running when it changed or not. A new page in a notebook tagged long ago is a new
  page, not "tagged before PaperDaemon was watching".
- A notebook that would start more than 10 jobs at once (created, uploaded or moved into a tagged folder) starts
  none; its pages come back one by one when you edit them.
- Changed pages are worked before new ones.
- Pause stops the jobs, not the daemon: while paused, what you write is still read and queued, and Start works
  the queue.
- PaperDaemon never puts a tag on a page by itself. Games no longer tag their pages, the adventure journal no
  longer gets "ignore", and a rebuilt document keeps the tags you put on it.
- Text and replies start at the toolbar line measured on the tablet (y 115).
- A full coloring page fills the whole screen, in the screen's exact shape.
- An erase that points at something not on the page goes back to the model instead of putting your request back.
- The page previews show exactly the screen: no strip below the page, no margin beside it, and a highlighter
  without its own color code is drawn in its color (pink was drawn yellow).

## 0.1.29

- Speak to a character and they answer, every time.
- Otherwise they talk on 25% to 75% of ordinary moves, by how chatty they are, and on 75% to 100% of dramatic ones.

## 0.1.28

- A finished game no longer holds its page: what you write there next is a request like any other, so "new game"
  starts one on that page.

## 0.1.27

- Game characters talk. Every character now speaks on a good share of turns (a third of ordinary moves for the
  quietest, half for the chattiest, more on a dramatic move, and nearly always when you speak to them); a quiet one
  used to say something on one move in fifty.

## 0.1.26

- Chess: after the opponent moves, your pieces stay in front of the board. Once the tablet had grouped them with
  the page's text, they were brought forward only inside that group, and the redrawn board covered them.
- Previews draw pictures in the tablet's own stacking order, so a picture the tablet shows underneath another is
  shown underneath here too.

## 0.1.25

- A model's location can be its API's own address, such as Google's OpenAI-compatible
  https://generativelanguage.googleapis.com/v1beta/openai: requests go to that address's routes rather than to a
  /v1 added after it. A server's plain address (http://host:port) works as before.

## 0.1.24

- The New lineup dialog's button says "Create lineup" (and Rename's "Rename"); it had no label at all.

## 0.1.23

- Ink the tablet ties to the typed text (it does that to writing near typed text) is read where the tablet shows
  it. It was read where it is stored, often far from where it appears, so the model saw it, ruled on it, wrote
  around it and pointed at it in the wrong place. Where a picture is tied to the same place, its record gives the
  exact position.

## 0.1.22

- Chess reads a piece where you put it, and a piece set back lands on its square. Once the tablet had grouped the
  page's pictures with its typed text, a moved piece was read a square off and put back far from its square.
- The opponent's name stands alone under its face; the rating is gone.

## 0.1.21

- A game takes the page it was asked on whole: what was on the page comes off first (the page is kept in its
  history), and nothing else is written on it, so no sentence lands on the board.

## 0.1.20

- A page whose path (the page, its notebook or a folder above it) carries tags of more than one lineup is no
  lineup's job: the daemon writes a note on it saying so, and skips it. Once its tags are one lineup's again, that
  lineup works it.

## 0.1.19

- A waiting job whose page was deleted is dropped, rather than listed as about to run.
- Jobs: the page has its own narrow column, a notebook's name that would wrap ends in an ellipsis, and what
  happened sits close beside them.

## 0.1.18

- A job that was running when PaperDaemon updated or restarted is handed over again at once, not shown as working
  for ever; a stuck claim on a page that lost its tag expires too.
- The Jobs list is quieter: no summary line, no headings and no "Today" row. Each job shows an icon at the left of
  its time (a check, a cross, an arrow past, a clock, or the spinner), and its columns keep their widths.

## 0.1.17

- Violins stay inside their axis, taper to a point and sit centered over their names.
- Scatter charts fit their axes to the points, draw every point whole and show one key (none for one series).
- The year map names its months and Mon / Wed / Fri, and every day's square is outlined.

## 0.1.16

- A game is played on the page where you asked for it. An adventure's character sheet and log follow that page.
- Chess: the board and the pieces line up; the classic piece shapes are back (the "cburnett" set, credited), in
  the board's colors; the opponent's face is larger, with its rating beside its name, and no narrator text
  appears on the board. The opponent may say its move.
- A game's notes in the notebook keep the opponent's memories, not its whole profile.
- Chart text is heavier and larger on every chart, and nothing runs together: pie labels keep apart, dense
  number axes keep fewer labels, a negative lollipop stays inside its chart.
- Kanban boards and marimekko charts show their contents again, agendas take times like "09:00", stat cards no
  longer fail, and waffle parts each have their own color.

## 0.1.15

- A job whose plan erases your request twice, once by naming it, is no longer reported as failed, and the request
  comes off the page.

## 0.1.14

- Posts from a site that can't be read directly (X without a post's link, Instagram, TikTok and others) are found
  with a web search and put on the page as cards, with every detail the search turns up: author, time, picture,
  likes or upvotes, replies, and the top comments.

## 0.1.13

- A reply that runs past the bottom of the screen is written whole. The page scrolls, but the answer was being cut
  at the screen's edge: the lines below it were dropped and the last one kept only the tops of its letters.

## 0.1.12

- The Language label rests on your language for five seconds, then shows three others for two seconds each, fading
  between them, and comes back.
- The exclamation mark is rounder and bolder, flashes twice and then stays still; its dot is drawn closed.

## 0.1.11

- Losing the internet is noticed within about half a minute (the connection to reMarkable now checks it is still
  answered), and the Overview shows one error for it. While offline, PaperDaemon tries once a minute and keeps that
  same single error up; it clears on the first success.

## 0.1.10

- The preferences note's timer runs, and the note expires, even with Windows' animation effects turned off; so do
  the Language label's words and the drawing of the lightbulb and the exclamation mark. Everything else still
  keeps still when Windows asks for less motion.
- The lightbulb and the exclamation mark draw themselves, stroke by stroke, whenever they appear.
- The timer bar stays inside the note's rounded corners.

## 0.1.9

- The "needs you" mark is a red exclamation mark in outline, with no ring around it.

## 0.1.8

- The note asking for your preferences appears once, after the library's first copy. On Settings it carries a thin
  bar along its bottom edge that runs down over 20 seconds; then the note and the sidebar's lightbulb are gone.
  Leaving Settings starts the 20 seconds over. If you are on Settings when the first copy finishes, the note slides
  into place and its lightbulb draws itself.
- The "needs you" mark on the Overview is a line drawing, like the lightbulb.

## 0.1.7

- With a notebook open, the mouse's back and forward buttons (and Alt+Left / Alt+Right) go to the pages you opened, in
  the order you opened them; back from the first one closes the notebook.
- Zoom the window with Ctrl + scroll, Ctrl + = and Ctrl + -, and Ctrl + 0 to reset. The zoom is remembered.

## 0.1.6

- The library's progress bar moves with the data that has arrived, not with the number of documents: a few large
  books no longer hold it still for minutes. Files a resumed copy finds already in place count too.

## 0.1.5

- PaperDaemon keeps your library's copy current the whole time it is open, whether or not it is working pages:
  it pulls when the tablet says something changed, on every reconnect, and on a timer only while that
  connection is down. Every update shows its bar on the Tablet tab, and the tab shows the changes when it is done.
- The daemon only watches for tagged pages, and each new or changed page is a job of its own.
- An update after the first copy no longer holds up what needs the library.
- An update (or any silent install) no longer puts a shortcut on the desktop; the installer adds one only when
  you tick its box.

## 0.1.4

- Copying your library is reliable. A copy that stops part way (PaperDaemon quits, an update installs, the network
  drops) carries on from where it stopped instead of starting over; files already copied are not fetched again,
  and they are never mistaken for unsent edits (0.1.3 and earlier set them aside as conflicts, over and over).
- A copy that fails is tried again on its own: after 30 seconds, then up to every five minutes.

## 0.1.3

- The "Check the tablet every" setting is gone. PaperDaemon updates its copy of your library when the tablet says
  something changed; it checks on a timer only while that connection is down.
- Check for updates shows a spinner beside the button while it asks; what it finds opens in its own window.
- Every Settings row is the same height, its control centered on its label.
- Pages that were already tagged when PaperDaemon started watching no longer appear in the Jobs list.
- The cycling Language label keeps one width, so the help mark beside it never moves; a long word fades out.
- Buttons sit the same distance below what they follow everywhere, setup's Continue included.
- A message line with nothing to say takes no room.
- The engine's local address is no longer shown in the sidebar or the host's log.

## 0.1.2

- Only pages tagged while PaperDaemon is watching become jobs. Pages that were already tagged when PaperDaemon first
  looked, or whose tag is older than that, are left alone; tagging one again brings it back.
- The sidebar shows the daemon's state as a word, without a dot.
- Every Settings row's label is centered on its control.
- A tall or narrow picture on the Decompose screen is centered above its details.
- Installing a newer or older version over the one you have keeps your data, settings and sign-ins. Only
  uninstalling removes them.

## 0.1.1

- Uninstalling removes PaperDaemon's data folder completely. In 0.1.0 an empty log file, and the folder holding
  it, could be left behind.
- A lineup without a tag yet is no longer reported as a problem, and the daemon runs either way.
- The help marks beside labels are drawn cleanly, and a tag's name sits under its label.

## 0.1.0

The first release, for Windows.

- Answers tagged reMarkable pages: answers in words, erasing, marking up words, drawings, charts (including
  points on a world or US outline map), month and week calendars, social posts, web search, pictures, coloring
  pages and pictures from the web, drawn as real pen strokes. It erases the request it carried out.
- Games on new pages right after the page that asked: chess against a cast of characters (Stockfish ships
  beside the app), a chat with a small town's residents, and an ink adventure.
- Lineups, all live at once and picked by the tag on a page: a text model (required: an API key, or your own
  server with an optional start script), an optional image model, optional web search, tags with their own
  prompts, and memories the model keeps about working for you. PaperDaemon never downloads a model or a server.
- Harnesses for model families, your own harnesses as JSON, skills folders or Python, and image workflows
  with LoRA adapters.
- A notepad per notebook that carries a conversation from page to page; a skipped job writes nothing to it,
  and the **Wipe notepad** button on the Notepads screen empties one.
- Connects to the reMarkable cloud by borrowing or stealing the reMarkable desktop app's login, kept in
  Windows' Credential Manager. Never permanently deletes anything in your cloud.
- A desktop window in 19 languages (what it writes on the tablet stays English), with defaults for
  temperature, clock, week start and country taken from Windows' region settings, and a tray.
- A per-user installer (not code-signed) with a Start menu entry and an optional desktop shortcut. PaperDaemon
  never starts with Windows, and checks for updates only when you ask (tray, or **Settings > Tools**).
- An uninstaller that removes everything PaperDaemon stored (the program, its data folder, its Credential
  Manager entries, its shortcuts and its WebView2 cache) and nothing else.
- A fast C decomposer that turns pictures into strokes, identical to its reference implementation.
