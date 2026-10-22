# Changelog

## 0.1.58

- Draw pages on the processor is a setting in Settings now, one for every lineup, under Network access. It was on each lineup's Text tab. A lineup that had it on turns it on for all.

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
