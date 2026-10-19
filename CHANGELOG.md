# Changelog

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
