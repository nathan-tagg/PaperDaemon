# Tasks: refine-from-dogfood-1106

## 1. Host

- [x] 1.1 Runaway guard: a loop is a chunk repeated back to back six times and over 400 characters
- [x] 1.2 Layout: places "on" a mark never crowd each other
- [x] 1.3 Brief: questions stay (how-to-answer included), only pure instructions come off, data is the user's notes;
      additions to a drawing go on its mark
- [x] 1.4 A picture landing over most of an old one replaces it (coloring pages, pasted pictures, charts)

## 2. Charts and lettering

- [x] 2.1 `trend` / `average` on line, step and bar charts: fitted and drawn by the host, named at their ends
- [x] 2.2 The host's chart figures carry the fitted trend
- [x] 2.3 Fractions, superscripts, subscripts and ≈ ± × ÷ √ ∞ π µ drawn as themselves (`symbols.install`)

## 3. Games

- [x] 3.1 Chess reads the player's ink alone (`inputarea.ink_png`)
- [x] 3.2 The reader copies the handwriting; a copy in notation is played as written

## 4. Search

- [x] 4.1 The two best results' pages are read for what bears on the question (web.readable); the brief:
      facts come from the results, and one they do not give is said not found

## 5. Proof

- [ ] 5.1 Released, then dogfooded in the False Mirror: a chart with a trend and an average, additions to a sketch, a
      question that says how to answer, a written pawn move in chess

## 6. Round 6 and the end of a chess game (0.2.24)

- [x] 6.1 The chess opponent has the last word when the game ends and stays on the page; a turn with no line of
      theirs keeps their face; a finished game takes no more moves; the receipt names the move once
- [x] 6.2 A reply moved under its question moves its plan box with it (no false "failed")
- [x] 6.3 The brief: a week takes `start`, "next week" starts on the user's first day; a habit tracker is a chart
- [x] 6.4 A ring keeps to the free paper round the words it circles
- [x] 6.5 A table entry longer than its column goes on two lines in its cell

## 7. Found re-judging rounds 4-6 (0.2.25)

- [x] 7.1 A draw offer is answered in the opponent's own voice
- [x] 7.2 A skipped page's note is plain words, no ids
- [x] 7.3 " -- " in lettered words is drawn as a dash
- [x] 7.4 A finished ink adventure says so on its last scene
- [x] 7.5 A move read clearly that is not legal is refused: erased, named in the receipt, told by the opponent; a
      dragged one too; chess receipts never empty, nothing said twice; *emphasis* marks off the strip
- [x] 7.6 The job's date line gives this week's and next week's first days by the user's week start
- [x] 7.7 A ring's open side keeps the open-paper end when the other side is tight
- [x] 7.8 An adventure turn where nothing in view changed keeps its picture without the card (0.2.26)
- [x] 7.9 The installer waits for the old app's executables to be free before copying (0.2.26)
- [x] 7.10 A draw's receipt says it once; the closing line's prompt leaves a pack character's voice alone; a number
      and its unit stay on one line (0.2.26)

## 8. Round 10 (0.2.27)

- [x] 8.1 Tool calls with a key written twice merge (harnesses/text._object): a calendar's lost event
- [x] 8.2 Line charts: every series channel in the series' order; no key for one line; legend labels never cut
- [x] 8.3 Off-palette part colors to the nearest tablet ink; a creature, person or scene to draw is an image
- [x] 8.4 The adventure logs its picture decision
- [x] 8.5 A paragraph holding the user's data and the request together is kept whole (0.2.28)

## 9. Round 12 (0.2.29)

- [x] 9.1 The rulings' categories: a request is an instruction alone; data with its request is a note
- [x] 9.2 A handwritten word alone on its line is listed as a line
- [x] 9.3 A checklist asked for is written as "- [ ] " lines (boxes to tick)
- [x] 9.4 The host refuses erasing a typed paragraph with a question mark as a request, and the paragraph a chart's
      numbers come from; checklist boxes a little taller than the capitals (0.2.30)

## 10. His rulings, 11-07

- [x] 10.1 The request paragraph comes off with its numbers (0.2.28-0.2.30's keep reverted); a question answered in
      words stays, one answered otherwise is the request it reads as
- [x] 10.2 Every group text gets at least one reply (messages._reply, table.force_speak)
- [x] 10.3 A strong chess opponent takes no draw in the opening, and says why
- [x] 10.4 A line chart's key is each line in its color and dash (markers on a field of their own)
- [x] 10.5 Select-all's counts are the selection's own after an editor reloads (keys unique per editor)
- [x] 10.6 Talk after a match goes to the opponent (games.after_game); anything else on a finished game's page is
      any page's job
- [x] 10.7 Death saves: a dying hero rolls (one success: up with 1 hit point; three failures: dead) or gives up;
      a death does not end the adventure (after_death: the great beyond, a return, a successor)
- [x] 10.8 A sketch is shown back once for a fix (RM_HOST_DRAW_LOOKS 1 by default)
- [x] 10.9 After a game turn the job instructions go back into the text model's memory (keep_prefix), local servers only
- [x] 10.10 Measured live: the first job after an adventure turn reads the instructions warm (round 15: its first
      turn 2.6 s, against about 15 s cold)
- [x] 10.11 Native typed checkboxes: the checkbox step (targets, checked), typed.restyle at commit, the plan checks
- [x] 10.12 Tablet test: checkboxes PaperDaemon set show, and tick and untick there afterwards (Checkbox test notebook,
      11-07: both pages ticked and unticked; the tablet stamps with the next item number, so restyles stamp one past the old)
- [x] 10.13 Round 15: the checkbox step's description (KeyError crashed every plan), a checkbox-only plan needs no place;
      after a match the words are the player's own and the model only says SAY or OTHER; the closing line always
      spoken; a failed death save is not undone by the story's healing; a tool's own fault logs its traceback
- [x] 10.14 Ambrose Tull, who plays every move for a level game (the engine's move nearest even, 32 looked over) and
      takes any draw at once, never saying so (games.chess aims_for / draw_offers; chess.level_move, aims, takes_draws)
- [x] 10.15 A real game against him: his moves keep the evaluation near even, and a draw offer is taken at once
      (11-09, DF200 on 0.2.35: 1.e4 e5 2.Nf3 Nf6, "Draw?" on move 3 -> a draw by agreement in 21 s)
- [x] 10.16 One design for every adventure page (the user, 11-07: "no design language, no consistency"): the column,
      the header, the type scale; no buttons, no page badges; page numbers in the contents and beside a person's
      name; no page for an empty section; portraits as strokes (each kept beside its picture, read back in one pass);
      six to a characters page; a journal page drawn again only when its picture changed; "Status" for "Now"; the
      loose ideas break between ideas; no kicker over a title and no heading over text that says what it is (the
      user, 11-08: "WHO THEY ARE" is "so cringe"; over-labeling is "the biggest obvious giveaway that something is AI")
- [x] 10.17 Portraits asked for on plain white ("light" came back cream, sage or gray)
- [ ] 10.18 On the tablet with him: a new adventure's pages, and an older one's after its next turn
- [x] 10.19 A figure carries words: a text part (text, x, y, size, anchor, angle) lettered on the figure's grid; the
      tool and the draw step say so (round 16, DF201: a "labeled diagram of the water cycle" came out with no word)
- [x] 10.20 A timeline takes dates (ISO, words, a year) and labels its ticks with the day (round 16, DF203: refused
      twice on a date string, then drawn empty)
- [x] 10.21 read_page: a look tool that reads another page of the notebook in words (typed exact, handwriting as read)
      while the model rules and plans (round 16, DF208: "my budget on page 1" got "I can't see page 1 from here")
- [x] 10.22 The write tool says an empty line is a blank line, for room to write by hand (round 16, DF206: a worksheet
      that promised room under each problem and left none)
- [x] 10.23 One list of named skills (the user, 11-09: "a proper name, not just '+3 perception'"; "spells should have an
      mp cost"; "skills, spells, special abilities, everything, should be 'skills'"): SKILL_NAMES, SPELLS and FEATS;
      magic points for a hero with a spell (a Magic cell); the engine takes a cast's points and refuses one unpaid for;
      the story's grants named with a cost; unify() reads an older hero's lists as one
- [x] 10.24 A leader line that ends inside its label's words is cut at the label's edge (round 17, DF211: "Chloroplast"
      struck through by the line that pointed at it)
- [x] 10.25 A loose idea under the scene is cut at a whole word with an ellipsis, never mid-word, and the prompts ask
      for a few words each (round 17, DF215: "pretending to be a c")
- [x] 10.26 A cast's magic points are taken once, by the engine: a negative "mp" from the story is refused with a note,
      and the prompt says the cost is already taken (round 17, DF215: Light cost 1 MP and the story took 1 more)
