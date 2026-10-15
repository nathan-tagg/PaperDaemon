# Changelog

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
