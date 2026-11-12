# Changelog

## 0.2.76

- A model run as a command-line program (`claude`) is held to PaperDaemon's output limit (16,384 tokens). It wasn't given one: on 11-12 Opus spent 14 minutes and about 128,000 tokens on one turn before it asked for anything.
- Looking at the page (reading another page, the changes, the marks) is counted by what the model writes, not by its hidden thinking. One long-thinking turn used to use the whole allowance, so the job's request to read page 2 was refused and it said it couldn't read the page.
- Handwriting on a long page is read. A page past about 5,000 units tall gave Windows' reader a picture too large to take, so none of its handwriting was read; it is now read in overlapping bands.

## 0.2.75

- The Daemon's notes no longer pile up on the tablet. The on-it and progress notes went up on copies of the page as it was when the job began, so every note reused the same stroke numbers, and the final note and the job's own drawing reused them again. The tablet keeps strokes it already has, so old notes stayed on the page (four signatures over two Daemon layers). Every note is now written into the page itself: it erases the last note the way the tablet erases, and its strokes get new numbers.

## 0.2.74

- Undo takes back only what was drawn. On 11-11 the model drew a scarf, looked, and undid with a count of 5. The whole scarf was one entry, so the undo also brought back the typed request it had just erased, and the job ended with no scarf.
- A drawing taken back after a look is drawn again before the job ends. If it isn't, the step fails and your request stays on the page.

## 0.2.73

- One progress bar. A Mirror sync (Ctrl+S, or closing a document) shows in the same bar as a job, along the bottom of the page and its cover, and the bar goes back to the job when the sync is through. There used to be a thin bar at the top for the sync and an orange one at the bottom for the job.

## 0.2.72

- What you write or erase in the Mirror and save (Ctrl+S) starts a job on a tagged page, the same as writing on the tablet. The save used to mark the page as already handled, so the edit reached the tablet and no job started.

## 0.2.71

- Weak never erases anything you wrote; replies only add, your request included. On Qwen3-VL 8B, asked which item in a list doesn't belong, it used to take your list off with the request.
- A checklist the model writes on one line ("- [ ] Milk - [ ] Eggs - [ ] Bread") is split into one line per item, each with its box.

## 0.2.70

- The Daemon works on one layer only: the page's Daemon layer. Every note wipes everything on it and goes there; PaperDaemon never removes, moves or adds back a layer, and makes one only when the page has none, added the way the tablet adds a layer (at the top). Its notes used to put back a layer entry the tablet had moved, and the tablet showed two Daemon layers with the same strokes.
- Ctrl+S on a Mirror page syncs both ways: your edits go up, then the tablet's latest comes down and the page shows it. With nothing edited in the window it used to do nothing.
- On a lineup with something switched off, the model can answer "that isn't offered here" with one plain call, and PaperDaemon writes the line ("Underlining the word bell isn't offered on this lineup."). Nothing of yours comes off. On Qwen3-VL 8B this replaced the copied lines and the claims that a word was underlined.

## 0.2.69

- An update waits for the job in hand. When you install an update, PaperDaemon now starts no new job, lets the one in hand finish (its final note and its push to the tablet included), and only then closes and updates. On 11-11 an update cut a job off between its work and its final note: the page kept no Daemon note, and its changes reached the tablet hours later.
- Weak works better on small models. Tested on Qwen3-VL 8B: asked to circle or underline in a sentence, it now leaves your sentence on the page and takes off only the request. It decides at temperature 0, so the same page goes the same way every time. Still open: it can say it underlined when it didn't, and on a "cross out the one that doesn't belong" list it takes the list off.
- On every lineup, the page message tells the model to answer only what asks for something and leave the rest as it is. A reply that names the page's internal ids ("para:2") is refused.

## 0.2.68

- A reply that writes your typed lines out again while taking them off the page is refused, and the model is told to leave your words where they are. The check was added in 0.2.62 but never saw the reply's words on the one-call answer, so it never ran there.

## 0.2.67

- Every time the Daemon writes to a page, it wipes the Daemon layer first: everything on it, whoever drew it. Nothing about what it wrote is kept beside the page any more. The record it kept (daemon-ink.json) hung erase marks on layers some pages no longer had, and the tablet drew nothing on those pages.
- The retry box sits on the Daemon's line, right-aligned after the signature. Under the line, at the left, it sat under the tablet's always-on dot. A tick in it counts on any layer.

## 0.2.66

- When a step that carries out your request fails, the model is told what failed and why, and writes you a few lines: what could not be done, the likely reason (weighing what the job found and any doubt you wrote on the page), and what to change. Your request stays for a retry. Before, the job only skipped, with the bare error in the Daemon's note: "Give me the latest top posts from r/PHAPrinting, not sure if that's the actual name" came back as "HTTPError".
- When Reddit refuses a feed (429), the reason says it does that both when requests come too fast and for a subreddit that doesn't exist or is private. A private, banned or missing subreddit that Reddit names as such says so.
- 0.2.64 refused to write an answer on a page that already had an earlier answer under counters the Daemon's notes had erased (Haiku page 3). An erased range now counts only for its own author's strokes, both when writing and when showing the page to the model. Your tablet draws such strokes, as the Sonnet page showed.
- A request line is taken off when the model names it in quote marks (`'para:1'`). The quotes made PaperDaemon look for those words on the page, so the request was kept and the note said "NOT DONE" though the job had worked.

## 0.2.64

- Answers show on the tablet after the Daemon's notes. PaperDaemon numbered each author's strokes on their own, so an answer took counters the Daemon's earlier notes had used and erased, and the tablet hides a stroke whose counter falls inside an erased range, whatever its author. Everything PaperDaemon writes (answers, notes, pictures, typed text, editor saves) is now numbered past every counter on the page, as the tablet numbers its own.

## 0.2.63

- The Daemon's note no longer leaves erase marks for a layer the page doesn't have. On the Sonnet page, such marks left the whole page undrawn on the tablet.

## 0.2.62

- A reply that writes out again a paragraph it is taking off the page is refused, and the model is told to leave the user's words where they are. Qwen3-VL 8B, asked to underline a word, erased the sentence and wrote it out again.
- Weak tells the model to say only what its steps do.

## 0.2.61

- Answers and the Daemon's notes show on the tablet again. Since 0.2.33 PaperDaemon wrote its strokes under author numbers 128 to 159. The tablet opened those pages but drew nothing under those numbers, and listed no Daemon layer. PaperDaemon now writes each kind of thing under a fixed number from 2 to 10: 3 for a written answer, 8 for the Daemon's note, 9 for a placed picture, 10 for typed text, and so on. It knows its own strokes by the page's author table, so pages written under 128 to 159 are still read as its own, and a page saved in the editor moves them to the new numbers.
- The Daemon layer is made the way the tablet makes a layer, with the second record the tablet writes for it. Without it, the tablet showed no Daemon layer.

## 0.2.60

- The line naming what a lineup doesn't offer now ends the model's instructions, where a small model still reads it, and it says only the request comes off the page. On 0.2.59, Qwen3-VL 8B asked to underline a word took the sentence off with the request and said the word was underlined.

## 0.2.59

- A model is told what its lineup doesn't offer (for Weak: sketches, mark-ups, social posts, pictures from the web, the long games), and asked for one of them, it writes one line saying it can't be done here. On Qwen3-VL 8B, asked to underline a word, it used to write the sentence and the request out again.

## 0.2.58

- Weak no longer offers mark-ups (underline, circle, highlight) or turning your own typed lines into checkboxes. On Qwen3-VL 8B both went wrong: asked to underline a word, it wrote the sentence out again; asked to make a typed list a checklist, it erased the list. With Weak, a checklist you ask for is written as a new list below yours.
- Checkboxes made of your own lines are now their own feature, so a harness can turn them off without turning off writing.

## 0.2.57

- The Text / Reasoning tab's Harness is a dropdown: Weak, Medium, Strong. Under it is the base's description and the models it was tested with. "Your harness" and "+ Add Harness" are gone, on the Image tab too.
- Capabilities is a box you type into, with a pill for each capability under it. Click the box to see what's left to add, type to narrow it, press Enter to add, and click × on a pill to remove it. Hovering a pill says what it tells PaperDaemon, and that the Image or Network tab is used instead when set. The warning about claiming what a model can't do is now at the foot of the Help page.
- Image generation works: with the Image tab empty and the capability added, a picture is asked of the text model's own server and taken from its answer. It is for servers that make pictures themselves, such as Gemini's image models. It has been tested against the reply formats those servers document, not yet against a real image model.
- On the command line, a model that answers in tool-call markup instead of the JSON it was asked for (Sonnet 5.5 sometimes does) is understood the first time, where it used to be asked twice more.

## 0.2.56

- A lineup you save takes effect without restarting PaperDaemon. Until now only the Settings screen's save reached the running loop: a new lineup's tag was not watched for, and a changed harness or capability not used, until the app started again.

## 0.2.55

- The Harness box for a text model is now a slider: Weak, Medium, Strong. Strong is for the strongest models such as Claude, Medium for 27B models and Gemini Flash, and Weak is new, for small models. The base's description shows under the slider. A harness file of your own is under Your harness.
- Under it are Capabilities: Vision, Web search, Image generation. They start from the harness and you can change them. A line says what the model can do, with a warning that ticking something it can't do will cause failed or wrong jobs. Help next to each label opens a page explaining both.
- When a lineup's Network tab has no search and its model can search the web, the model looks facts up itself. PaperDaemon turns on the `claude` program's own search and the Anthropic API's. With neither, the model is told facts can't be looked up. The Image and Network tabs say that what they set is used instead of the model's own.
- Image generation can't be ticked yet: PaperDaemon can't take a picture from a text model's answer.

## 0.2.54

- PaperDaemon can make a notebook on the tablet itself, not only in the False Mirror, when "Edit the Mirror" is on in Settings. The notebook gets its name, folder and tags and is sent to the tablet at once. There is no button for it in the window yet.
- The descriptions under the Harness box are rewritten in plain words: what the harness is built for, what the model must be able to do, and what it costs.
- A page with only typed text on it is sent to the model as text, with no picture, on every harness. Lean Default already did this; now Default does too, so a local model skips encoding an image it doesn't need.
- A lineup on the Anthropic API asks Anthropic to cache. Until now it paid full price for every token on every call. The job log shows how many tokens came from the cache.
- On the command line, the page is worded the same way on every call of a job, so the start of a later call can match the call before and come from the provider's cache.

## 0.2.53

- Under a lineup's Harness box is the picked harness's own description: what it is for, what the model must be able to do on it and what goes wrong with one that cannot, and what it costs to run (Default on a strong model uses several times the tokens Lean Default does). The text is the harness file's `notes`, so a harness of your own shows yours.
- "llama.cpp - Qwen 3.6 27B" and "llama.cpp - Qwen 3.8 27B" are folded into "Default": they were the same thing under two more names. Default's description says it was designed for Qwen 3 models running in llama.cpp. A lineup, or a harness of your own, that named one of them now names Default, and works as it did.

## 0.2.52

- An update removes the earlier version's engine files before it writes the new ones. Until now it wrote over them and left behind any file the new version no longer has, so after updating to 0.2.51 the Harness box still listed "Claude Opus 5.5", "Claude Sonnet 5.5" and "Claude Haiku 5.5", which that version had removed. Your settings and data are in their own folder and are not touched.

## 0.2.51

- A lineup's harness is the one you pick, and nothing else. "Automatic (from the model's name)" is gone: PaperDaemon no longer chooses a harness from a model's name, a server's report or a start script. The Harness box is a plain list that always shows a harness; a new lineup starts on "Default". A lineup that was on Automatic keeps the harness it was running on, now shown by name.
- "Built in" is named "Default", beside "Lean Default (stronger models only)". The harnesses "Claude Opus 5.5", "Claude Sonnet 5.5" and "Claude Haiku 5.5" are gone: they were the same thing as Lean Default, which a lineup that used one now names.

## 0.2.50

- On a lean lineup a sketch is no longer shown back to the model for a fix. The look was a whole further call, so a job of words and a sketch is now one call.
- The Command box of a command-line lineup is as wide as the Source and Harness boxes around it. In 0.2.48 it ran the whole width of the tab.

## 0.2.49

- A sketch that comes with a lean lineup's plan sits right under what it follows. It was fitted into the middle of its place, and under a few sentences that place is the rest of the page, so the drawing landed half a page down.

## 0.2.48

- A command-line lineup has one box, Command, and it holds the whole command: `claude --model claude-opus-5-5 --effort medium`. The Model box is gone, because how a model is named is the program's own syntax, and no harness sets an effort or adds a model any more: both are yours to type. PaperDaemon starts the program itself, with no shell, and adds only what carries a request in and its answer out. A lineup saved with a model beside its command becomes the command naming that model. If your lineup relied on its harness for medium effort, add `--effort medium` to the command.
- One harness a model. The Harness box offers "Claude Opus 5.5", "Claude Sonnet 5.5" and "Claude Haiku 5.5", each picked by the model the command names, and no longer lists the `claude` program's own data beside them.
- "Lean Default (stronger models only)", a harness for a model that needs little telling and is dear to call; the three Claude harnesses build on it. A lean lineup gets a short job description, each turn carries only the calls it may make instead of the whole tool list, a page of typed text is sent as its text with no picture, and a job's words or sketch come back in the plan itself, so most jobs are one call where they were three or four. A chart or a calendar still takes a second call, and a sketch is still shown back once.
- A call to `claude` is one request where it was two. Asked to check its answer against a schema, the program made a second request for every answer; PaperDaemon now reads the answer's JSON and checks it itself.
- A job's log says, for each call to a hosted or command-line model, how many tokens the model read anew, how many came from the provider's cache, and how many it wrote, as it already did for a local model.

## 0.2.47

- An argument you type in a command-line lineup's Command stands over what the harness would add: with the command `claude --effort high`, the model runs at high effort though its harness says medium. The same goes for any argument a harness adds as an option.
- Editing a Mirror page: a setting changed in the editor (a paragraph's style, a layer's name, the typed text shown or hidden) is marked only just newer than the one it replaces. Since 0.2.43 it was marked newer than everything on the page, which on a page holding a large drawing could have made it win over a change you made on the tablet afterwards.

## 0.2.46

- A checklist with one item ticked is no longer reported as failed. 0.2.45 made the checkboxes, then counted the ticked paragraph twice, said one paragraph was not found and left a retry box on the page.
- Receipts are in plain words throughout: "make 4 checkboxes, 1 of them ticked" and "highlight 'The harbor master rings a bell at noon.'" instead of paragraphs named by their ids.

## 0.2.45

- "Make these checkboxes, and tick the plants one" works. When two steps of a job named the same typed paragraph (a checkbox, then a ticked one), the whole checklist failed with "a paragraph's style did not read back"; the paragraph now takes the last style named for it.
- A job's receipt, the line at the top of the page and in the Jobs list, says what was erased in plain words: "erase 11 ink marks" instead of every mark by its number, twice over.
- The Concord: an order the rules do not allow is shown back with the rules' own reason ("not allowed: no militia on a coast at The Archive") instead of "no unit of yours" at a shire where your unit stands. A unit of yours that is driven out says by whom and where it went.

## 0.2.44

- A page whose typed text was left tangled by the collision fixed in 0.2.43 shows its words again. They are read in an order that may not be the tablet's own, so the editor refuses to change them; deleting all of the page's text is taken, and clears the tangle for good.
- A job that erased the request it was written for no longer reports a failed page render. The emptied page was refused by the renderer, the job noted a quiet failure, and the model was told the page could not be seen; an empty page is now drawn as an empty sheet.
- The Jobs list reads well in a narrow place. As a tab of the Lineup screen in a window of middling width its note column shrank to a word a line; it now lays each job out as a short block whenever the list itself is narrow.
- The Concord: a build or disband you write is shown on your page with what came of it, and the season's news about you comes first. On the Seasons page the later rows of a long line no longer run past the right margin.

## 0.2.43

- Editing a Mirror page no longer collides with the tablet. What PaperDaemon wrote on a tablet page was numbered as if the tablet had written it, so when a page was written on here and on the tablet within the same minute, before the tablet had synced, two different things took the same number: typed words landed inside another line, a line lost its first letters, and the text could be left in a state nothing could edit. The editor now numbers what it writes under a number of its own, which the tablet opens like any other and can never hand out itself. Your strokes drawn in the editor are still yours, not the daemon's.
- A page whose typed text was already left tangled by this is told apart from a page with no text: the engine says it holds text it cannot read, refuses to edit that text, and takes the one edit that is still exact, all of its typed text deleted. The window does not show this yet.

## 0.2.42

- A lineup's text model can be a command line. Source now offers "Command line" beside "API key" and "Host locally": you give the command as you would type it in a terminal, and PaperDaemon runs it once for each turn, hands it the request and reads what it prints. It replaces the "Claude Code" provider of 0.2.39, which sat under "API key" though no key was involved; a lineup that used it becomes a command-line lineup with the command `claude` and works as before.
- Nothing in the application is made for one program. How a program is spoken to (its arguments, how it takes a picture, where its answer is in what it prints, how to ask whether it is signed in, where it sends a page) is written in a harness, in its new `cli` field, like everything else a harness says; the harness guide explains it with an example. A program with no harness is given the request on its input and its printed text is the answer. Two harnesses ship for the command `claude`.
- The Concord: a promise made in a letter counts from that same season. A family that promised to keep clear of a harbor "this season" moved on it anyway, because its orders had been written before the letter arrived; its orders are now written again once it promises. A promise of no attack also covers your harbors and the shire it names.

## 0.2.41

- The Concord: a unit that is dislodged gives no support. A fleet driven out of its shire still counted its support for another family's move, even when the blow came from the shire it was supporting into; in the first real game that turned a move that should have gone in into a stand-off.
- A family's unasked letter is about the season to come. They were written from the orders just played, so one spoke of "your fleet at Harbor Row" after taking Harbor Row itself, and another asked for help toward one of your own harbors. A family now writes after its next orders are decided, is told the order it wants from you ("Fogwater supports The Tower to Merrow Point"), never asks for your own harbor, and addresses you by your family's name instead of a name it made up.
- A letter is never cut at the foot of the letters page: each page takes the letters that fit whole, and a new page is added for the rest.
- On the map every name, ring and counter stays inside its own shire, moved to where the shire has room; a harbor you hold with another family's unit on it shows your mark before the ring. A move that met a unit that stayed is "turned back".

## 0.2.40

- The Concord of Merrow Bay starts. Its first real start failed while saving the game and left the page blank; the game is now kept in the notepad like the others.
- A game that fails to start puts the page back as it was, request and all.
- On the Concord's map every shire's name stays inside its own borders, on two lines where one is too long.

## 0.2.39

- A lineup's text model can be Claude Code, the command-line program installed on this computer. Pick "Claude Code" as the provider and name the model (claude-opus-5-5, or opus, sonnet, haiku): PaperDaemon starts the program as it is, hands it the page and reads its answer. It never touches the program's sign-in: Claude Code signs in by itself, as you, and the use is yours under your own plan. Each run has none of the program's own tools and none of your Claude Code settings, hooks or connected services, and keeps no session. A new harness, "Claude Opus 5.5, medium effort", is picked for that model by itself; the effort is a field of the harness, so another harness can set another.
- A new game: the Concord of Merrow Bay. Ask for it on a page ("start the Concord", or "start the Concord as the Hales") and the page becomes a map of the bay's twenty-eight shires, with the orders, letters and seasons pages right after it. Seven families hold the bay; you play one, six of the cast play the others. Each season you write an order for each of your fleets and militias in plain words under the rule of the orders page (hold, move, support, convoy), and every family's orders resolve at once by the rules when the page syncs: a support cut by an attack, a move won by the greater strength and stood off by an equal one, no family dislodging its own. Harbors count at each autumn; eleven win, or the most after the tenth autumn.
- The whole game is letters. Write to a family on the letters page, its name first, and it answers in its own voice, knowing its standing and the orders it has already decided; it may promise support, peace or a shire left empty, and it keeps or breaks its word by character. A promise kept binds its orders; one broken is remembered against it. A family also writes unasked when you attacked it or when it wants your hand.

## 0.2.38

- The window comes back on the screen and in the folder it showed, every time. What the window remembers for itself (the screen, the folder of a library screen, the Decompose page size, a note seen) is now kept by PaperDaemon in its data folder instead of the web view's own storage, which in some installs forgets everything at a restart: on the maintainer's machine every update brought the window back on the Overview.

## 0.2.37

- A cast costs its magic points once. The engine takes a spell's cost when it is cast; the story used to take it a second time, so Light at 1 MP cost 2. The sheet's Magic cell now shows what is really left.
- A leader line stops at its label. In a labeled sketch, a line that ended among the letters of the word it pointed at struck the word through; it now ends just before the word.
- A loose idea under an adventure's scene is never cut mid-word: a long one ends at a whole word, and the game master is asked for a few words each.

## 0.2.36

- Ink Adventure's skills are one list. Every entry has a proper name (Keen Eye, Sneak Attack, Fire Bolt), says what it lets the hero do, and shows its figure at the right: the check a trained skill is good at with its bonus, or a spell's cost in magic points. A hero with a spell has magic points beside their hit points; a cast costs its points, one the hero cannot pay for does not happen, and magic comes back by rest. An older adventure's hero is read the same way.
- The window opens where you left it: its position, size and whether it was maximized are remembered, and so are the screen it showed and, on the Mirror and the False Mirror, the folder it was in. An update's restart puts it all back. A remembered place on a monitor that is gone is ignored.
- A sketch can carry words. A diagram asked for with labels used to come out mute, because the figure had no part that could hold text; now a text part is lettered on the figure like any other, at the size and anchor the model names.
- A timeline takes dates. "Kickoff January 5, design review February 2" was refused twice and then drawn as an empty axis; events are now placed by their dates, by a year or by a number, and each tick says the day.
- The model can read another page of the notebook while it rules and plans: its typed text, exact, and its handwriting as read. "Using my budget on page 1" is answered from page 1, not with a request to type it again.
- A worksheet leaves room to work: the model is told that an empty line is a blank line, so "room under each problem" is real space.

## 0.2.35

- An Ink Adventure's pages share one design. Every page keeps to one column, the width of the scene's picture and of the tablet's own typed text; each has its title and a thin rule under it at the same height; one set of type sizes runs through them all. Nothing is drawn as a button any more (a notebook page can't be tapped), no "p. 5" badges hang off boxes, and nothing carries a label for what it already says.
- The journal opens with a contents under the adventure's own name: every page of the game by name, the scene, the sheet and the story among them, each with its page number after a dotted line. On the characters page each person's page number is at the right of their name. In a game played as its own PDF those same lines are its links.
- Portraits are drawn in ink, decomposed like the scene, on the characters page and on each person's own page. A characters page holds six people, which keeps it about as heavy as a scene. New portraits are asked for on plain white.
- Quests and Lore get a page, and a line in the contents, once there is something on them. No page counts what is on it. What the hero knows of a person is a list, a line each, and a person's page shows only what is known.
- In the page editor, the PDF link under the pointer is lit light yellow again, and darker while it is pressed, both in the view and while editing.

## 0.2.34

- The page editor gives back the graphics memory its work took. Erasing grew the editor's stores on the card and they never shrank while the page stayed open. Now, about a second and a half after you stop, they are laid out again at the size the page needs: on a page of 30,000 strokes, from 76 MB after three heavy swipes to 25 MB; on one of 150,000, from 325 MB to 112 MB. It is done in idle moments, never long enough to be felt, and it stops the moment you touch the page. The page looks exactly as it did, undo works across it, and opening a page is no slower.

## 0.2.33

- You can draw on the daemon's layer and keep what you draw. In the page editor its layer can be chosen like any other, and erased and selected on; it stays at the bottom of the list. The daemon's next note erases only its own strokes, its byte 134, and leaves yours. On the tablet, too, what you draw on that layer stays and is read as the page's. Until now everything on that layer went with the next note.
- On a page whose last note came before 0.2.32, everything on the daemon's layer still counts as the daemon's until its first note under its byte. The first stroke you save there in the editor turns that old note into the daemon's own (the same strokes, under 134), so your stroke stays.
- A note landing on a page open in the editor replaces the last note and keeps what you drew on that layer, saved or not.
- A new face in Merrow Bay: Ambrose Tull, the harbor's weighmaster, at the library chess club on Thursdays. Every move, he plays the engine's move nearest an even game, whoever is ahead, and he takes a draw the moment you offer one. He never says so.

## 0.2.32

- "Make these a checklist" works: every plan with a checkbox step was refused with an error (KeyError) in 0.2.31, and the raw error showed in the page's receipt.
- After a chess match, what the opponent answers is your own words, as typed or as written: asked for the words themselves, the reader once put "You should have taken more time" in place of "Start a new game against someone stronger", erased the request, and the opponent answered words nobody wrote. A request written there now goes to a job like any page's.
- A chess opponent always has a closing word when the game ends: after a resignation the table could leave them silent.
- A failed death save leaves the hero dying: the story's healing on that turn is not taken, so a failure and "+1 hit point" no longer get the hero up without a success.
- The right author bytes everywhere: an adventure's traced scene is 130 (it was 128), the daemon's footer 134, the studio's decompositions 130, and a page's overflow strokes keep theirs. A page of the False Mirror saved from the editor keeps PaperDaemon's bytes: written anew, its answers, chess pieces and pictures all became yours (author 1).
- A fault inside PaperDaemon during a model's turn writes where it happened to the host log.

## 0.2.31

- PaperDaemon's strokes say whose they are and what they were, in their author byte: 100 and five bits of what each is -- 129 a written answer, 130 a picture traced into strokes, 131 a chart, calendar or table, 132 a sketch, 133 a mark-up, 134 the daemon's note, 135 a placed picture, 136 typed text. Your tablet writes as 1. Nothing is kept beside the page: the byte says it, and nothing is judged by how the strokes look. A stroke's author is one byte, and the tablet opens a page with 1-159, 175, 191, 207, 212 and 240-255 (measured on the tablet, a page per number from 1 to 512); every one of PaperDaemon's opens.
- Everything on the daemon's layer is the daemon's; no stroke anywhere is judged by how its points look (a stroke drawn with a mouse looked machine-made and could be erased).
- The Mirror's whole-page save keeps the daemon's layer, whatever author made it.
- A request with the numbers it works from comes off once its chart is on the page, as any request does; your other paragraphs stay. 0.2.28 to 0.2.30 kept it.
- A question asking for something done ("Can you draw a cat?") comes off once it is done; a question answered in words stays.
- Talk after a chess match goes to the opponent: what you write to them on the finished game's page comes off and they answer in their own voice. Anything else written there (a new game, a request) is a job like any page's.
- A strong chess opponent (1600 and up) turns down a draw in the first 20 moves unless it stands clearly worse, and says why: a 2600 took a draw on move 3 of an even game.
- An adventure hero at 0 hit points is dying, not dead: the page offers "Roll a death save" or "Give up". One success and the hero is up with 1 hit point; three failures, or giving up, and the hero dies -- and the story goes on, as the model tells it: the great beyond, a return, a successor who takes up the quest.
- Every group text gets at least one reply: each member may answer and none has to, but when nobody would, the one the message names (else the chattiest) answers.
- A sketch is shown back to the model once for a fix: "a lighthouse on a rock" came out with no rock, and nothing looked.
- A typed list you ask to be a checklist takes the tablet's own checkboxes, where it is, instead of being drawn again beside itself.
- After a game turn, PaperDaemon puts its instructions back into a local text model's memory in the background, so the next job (and a start script's save across a picture swap) finds them read instead of reading them cold.
- A line chart's key draws each line in its color and dash: Liam's dashed line was keyed as a square with a dashed edge.
- Select all (Ctrl+A) in the page editor shows that selection's counts; after switching windows it could show the counts of the selection before.

## 0.2.30

- The paragraph a chart is drawn from stays on the page, even with the request in it: the job refuses a plan that would erase a paragraph holding the chart's numbers. Brief wording alone did not stop it, three times running.
- A typed question stays, whatever else it says: a paragraph with a question mark is never erased as a request ("What should I pack...? Give me a checklist." was erased once).
- Checklist boxes are a little taller than the capitals, big enough to tick with a pen; they were about a lowercase letter tall.

## 0.2.29

- A paragraph with your data and the request in it ("Mia: Mon 20, Tue 35 ... Make a line chart of both.") is ruled your data and stays; 0.2.28's rule was read after the paragraph had already been called a request, and it was still erased.
- A handwritten word alone on its line ("eggs" in a list) is read as a line of your handwriting: listed as a mark with its stroke count, it was answered as "Eggs (9)".
- A checklist you ask for is written with a box to tick on each item; it came back as a plain list.

## 0.2.28

- A paragraph that holds your data and the request together ("Reading minutes this week. Mia: Mon 20, ... Make a line chart of both.") stays on the page: it was erased whole, and the numbers were left only as a chart's lines.

## 0.2.27

- A calendar keeps every event you gave it: "Dec 12 work party" was lost, and a three-day visit showed on one day. The model wrote those days twice (their events, then their on-this-day card), and only the second entry was read; now both are.
- A line chart's markers ride their own lines: with series not in alphabetical order, one line's dashes and markers were drawn on the other ("Mia" through "Liam"'s squares). A chart of one line has no key, and a key's names are never cut ("Reading mi...").
- A drawing's color the tablet has no pen for is drawn in the nearest one it has: an orange fox was drawn black.
- A creature, a person or a scene you ask to have drawn is made as a picture, not built from simple shapes; a sketch is for simple shapes and additions to a drawing.
- An adventure turn's log says whether its picture was kept, edited or painted anew, and why.

## 0.2.26

- An ink adventure turn where nothing in view changed (words were said, a look, a thought) keeps its picture: no repaint and no hand-over of the graphics card. A turn that only talked spent 40 seconds on an "edit" that changed nothing the page shows, and the next job's text model came back cold.
- An update waits for the old PaperDaemon to let go of its files before copying the new ones: one stopped on "Error opening file for writing ... PaperDaemon.exe" until Retry was pressed.
- A chess draw's receipt says it once ("Game over: a draw by agreement."); it said "a draw, agreed; Game over: draw agreed, a draw."
- An opponent's closing line is theirs to choose again: 0.2.25 asked for words, not a sound, which fought a cast pack's character who keeps a goat's act.
- A number and the short word after it stay on one line in an answer ("3 pm", "10 kg"): "pm." sat alone at the start of a line.

## 0.2.25

- A chess move that is not legal is refused out loud: written or typed ("Ke3" with the king on e1), it comes off the page, the receipt names it, and the opponent tells you in their own words; a piece dragged where it cannot go is put back and the opponent says so. It was passed over in silence, the typed move left on the page.
- A chess opponent answers a draw offer in their own voice: taken, their last word says so; refused, they say why and the game goes on. Every character used to answer with the same fixed line ("A draw? Fine by me.").
- Chess receipts say each thing once and are never empty: a refused draw offer left "chess:" with nothing after it, and a resignation was said twice.
- An opponent's closing line is words, drawn without a model's asterisks ("*Baa.*").
- A week page for next week starts on the first day of your week: the job now says which days this week and next week begin, so the model no longer works it out (it started next week on a Monday for a week that starts on Sunday).
- A ring round words at the end of a line keeps its round end past the last letter; only the side with a word close beside it is drawn tight.
- A skipped page's note says why in plain words: it showed ids like "line:1, mark:11".
- A typewriter's dash between words (" -- ") in an answer is drawn as a real dash.
- An ink adventure that is over says so on its last scene ("The end: a victory.", "The end: Elara Vane has fallen.") instead of offering ideas for a next move no game would take.

## 0.2.24

- A chess opponent stays at the table when the game ends and has the last word, in their own voice and true to how it ended: a winner's, a loser's or a draw's. A game won on your move or ended by resigning left the page with no opponent at all. Without a text model their face stays, in the mood the end left them in.
- The opponent's face stays on the page through a turn with nothing from them (a move refused and put back, writing that could not be read); it used to vanish until their next move.
- A finished chess game takes no more moves: after a resignation or an agreed draw the board still has legal moves, and one written afterward was played into the finished game.
- A chess receipt names the opponent's move once ("Rook played Nf6"), without how the move was chosen.
- An answer written under its question is no longer reported as failed, with a retry box, when it landed fine: the check looked for it where the plan had first put it, at the foot of the page.
- A week page for next week starts on the first day of your next week; it started today, so "Saturday: soccer" landed on this Saturday. A habit tracker is a tracker grid, not a month calendar with the habits written into every day.
- A ring round words in a paragraph keeps off the words around it: round a date that wrapped, it cut the "by" before it, and its top edge ran through the line above like a strike-through.
- A table entry too long for its column goes on two lines in its cell instead of being cut off ("Set table, Recyclin").

## 0.2.23

- An ink adventure's scene page has no line over the place to write: the story's cell, then the rule, and the page under it is yours.
- A checklist reads as lines of the page's text: trimmed to its boxes and words, at the typed text's size, its left edge on the text column's, its boxes square. It was drawn as wide as the page, its boxes at the page's far left and its words larger than the typed lines above it.
- The adventure's journal ends an entry at a whole sentence, not mid-thought ("...on a stand, and...").
- Dashes are drawn as dashes: an em dash came out "--".

## 0.2.22

- A reply goes right under the question it answers when the paper there holds it, even with a note further down the page. It went below everything on the page: under a note to someone at the page's foot, a screen and a half below its question, with white paper between them. A reply too tall for that space still goes below everything.
- A game's turn says in the log where its time went (the model, the pictures and the page), and a calendar says how long its on-this-day facts took to fetch.
- A chart whose numbers the plan already gave is drawn from them at once. A plan that carried the chart's whole spec was refused for it, made again, and the chart's own turn then wrote the same spec a third time: four turns and 20 seconds to add one month to a chart, now one.

## 0.2.21

- A job's note says what was written, never what the plan guessed before it looked: when a search found nothing, the page said "I couldn't look that up just now" while the note beside it quoted the plan's own guess at the answer.

## 0.2.20

- A search that finds nothing says so. When the search engines refuse (asked too often: "too many requests", a CAPTCHA), the answer now says it could not look the question up just now, with the engines' reasons in the job's note, instead of writing the facts from memory: an answer named seven states the eclipse never crosses.
- A question stays on the page whatever else its paragraph says: "When is the next eclipse...? Please look it up." was taken for a plain instruction and erased.
- A drawing's parts can be drawn in the tablet's inks: "add red apples" draws them red, not black.
- The decomposer's identity test covers its two busy test pictures as well (their records were missing).

## 0.2.19

- An answer that looks something up is written from the pages found, not only their one-line snippets: the two best results are read for the paragraphs that bear on the question. An answer about the next total eclipse named a dozen states its path never crosses. What the results do not say, the answer says it could not find, rather than filling it in from memory.
- A chart's key sits above the chart in a row, clear of the data: in the chart's top-left corner it covered the first bars and points.
- Additions to a drawing go where they belong on it: the daemon is told the drawing's parts (a snowman's head, body and base) and draws on them in the page's own numbers, and what it draws stays exactly where it drew it. A hat, sitting above the snowman's head and so outside the snowman's box, was scaled to the whole snowman and landed on its body; a chimney ended up inside the wall.
- Writing addressed to someone else ("Dad - circle the one you like!") is theirs to do: the daemon keeps it and leaves it alone. A circle or highlight that does not say what it marks is sent back to the model before anything runs, instead of failing after.
- A plan with several problems hears about all of them at once, not one a turn, and a coloring page may name the image harness's workflow as a picture can.
- The daemon no longer stops with an error when it reads a page in the instant it is being written; the job's last note always replaces its progress line.

## 0.2.18

- Typed text shows on every page, pictures and all. On a page holding a picture (a capture, a coloring page, a chart) the viewer and the editor showed none of the page's typed text, and saving such a page from the editor took the text off it. A save that carries no text now leaves the page's text exactly as it is, as the Mirror's always has.
- A chart's trend line and average line are worked out by PaperDaemon, never by the model: ask for a trend or an average on a line, step or bar chart and they are drawn dashed and dotted in the series' ink, named at their ends. A model's own trend ran "down, 132 to 90" through bills whose fit runs 119 to 123, up; the words written about a chart now get the fitted trend with its other figures. An average line no longer stops the job as "the model kept repeating itself".
- Several additions to one drawing (a hat, a scarf and buttons for the snowman) are drawn on it, instead of the plan being refused as overlapping. An addition to a drawing is put on the drawing, even where it sticks out past it.
- The daemon erases only an instruction it has carried out. A question stays even when it says how to answer, and the facts and numbers a request works from (the bills a chart was made from, a schedule put on a calendar) stay on the page.
- A coloring page or a picture made again replaces the old one, as a chart redone already did; the old one stayed under it.
- Fractions, superscripts and signs are written as themselves: "6½" was written "61/2", "¾" came out "34", and "≈", "±", "√", "π" and "∞" vanished.
- Chess reads a written move from the player's writing alone and plays notation as written: "c3" moved a knight to c3 when the pawn could go there too, and the opponent's own last words ("Bishop to a6. I do hope the arithmetic is sound.") were once taken for the player's.
- Chess moves can be typed: "e4", "Nxc2", "O-O" typed on the game's page is played as it is, read exactly with no model asked, and comes off once read, as written moves do. Anything else typed (a resignation, a draw offer, a remark to the opponent) is read by the text model, the way handwriting is read by the vision model.
- A web picture is never taken from a stock-photo site, whose pictures are watermarked previews ("a real photo" came back with the site's name across it). Wikimedia's are tried first.

## 0.2.17

- The pointer: the text tool is now the first in the bar, an arrow. It is the I-beam over text it can select or type into, and the hand over a PDF's or a book's link: a click follows the link (to its page, or the address in the browser), and a drag selects the link's words instead. With a pen or an eraser in hand, Ctrl and a click follow a link, and the pointer over one says so. The shortcut sheet lists it.
- A click with the highlighter leaves a mark: a small square as wide as the highlighter, on the tablet too. A highlighter stroke of one place drew nothing anywhere.
- The daemon's drawings stay on the page. A job's commit and the daemon's progress note could write the same page at the same moment, and the note's write took out what the commit had just drawn (a cat's whiskers, there and then gone). Every write of a page now waits for the one before it: the host's, the daemon's notes and the editor's saves.
- A drawing added to a sketch lands where it was drawn: a chimney on the roof, apples in the tree. It was fitted into the sketch's box, scaled up and centered, and missed.
- A reply is never written smaller near the foot of the page: it keeps the typed text's size, and the page extends below.
- An ink adventure's scene page: the story in a cell as wide as the picture, then an italic line chosen by the scene's mood ("Think quickly…", "Describe your action…") over a rule as wide as the cells, where to answer. The ideas under the story never stop mid-phrase.
- An adventure hero's sheet lists only the skills they have, each once, with its bonus, and the story can give them skills and spells of their own, each with what it lets them do; the game master is told of them every turn.
- The daemon keeps a question even when it also says how to answer it ("in three short paragraphs"), and takes writing addressed to someone else (a person, or another assistant) as a note, not a request.
- The start-script help, and its "Ask AI for help" prompts, suggest keeping the text model's prompt cache across picture swaps with llama-server's slot save and restore, so the first job after a picture starts warm.

## 0.2.16

- The dotted lines stay on the page: the top of the safe area runs from the page's left edge to its right, and the screen's side edges from its top to its foot, never across the gray around the page.

## 0.2.15

- Straight lines: with a pen in hand, 1 makes the next stroke a straight line -- a drag, or two clicks, from one end to the other, Alt snapping it to 15° steps -- and once it is drawn the pen is freehand again. 1 again, or Esc, goes back without drawing one; mid shape, 1 makes the shape under way a line from the same start.
- Holding Shift in the middle of a stroke no longer turns the pointer into the eraser's ring. The stroke never erased; now the pointer says so too.

## 0.2.14

- The dotted lines show only while the view moves -- a pan, a scroll or a zoom -- and go a moment after it stops: the screen's side edges, and the top of the safe area that 0.2.12 added and left on every page. Opening or turning to a page shows none.

## 0.2.13

- The window lays out typed text exactly as the engine does, so a reply never lands on typed text there. It measured a line whole at the type's own size, about 1% wider than the engine's measure, and wrapped a line the engine had fitted: the window showed one more line of typed text than the engine knew of, and a reply placed under the engine's last line sat on the window's. Each letter is now measured and placed the engine's way, equal to the unit.
- An on-this-day card joins its haiku's lines with spaces only. 0.2.12 put a comma at each break, and a verse line often breaks mid-phrase.

## 0.2.12

- A month calendar's days are never colored by what is on them. Holidays, birthdays and appointments are all one-line pills under the day's number, none more important than another; with the weather, the sky colors only the weather block above its rule; without it there is no weather block and no rule. The on-this-day card is docked at the day's foot, and is left off rather than ever overlapping the day's items. A holiday colored its whole day, and the card was drawn over it.
- An on-this-day card reads as one flowing text: the haiku's lines run together and wrap at the card's width, with no line breaks and no indented run-overs, on the month and on the week.
- A month calendar fits its page. Drawn the safe area's height, then widened to its box with its title above, it ran past the foot of the page (2,412 tall on a 2,160 page); a month that would is drawn shorter until it fits.
- The editor shows the top of the safe area as a subtle dashed line across the page, where the tablet's toolbar ends when it is docked at the top, moving with the page's zoom as the screen's side edges do.

## 0.2.11

- The daemon's handwritten replies match the typed text by their ink: their lowercase is as tall as a typed paragraph's. 0.2.10 matched the letters' center lines, and with the pen's own thickness the replies still stood larger, their capitals nearly half again the typed ones. Lines stay 45 apart with 25 more between paragraphs, and a reply's first line sits where the next typed paragraph would, so the space under the typed text is a typed paragraph's every time.

## 0.2.10

- A page's pictures show as soon as they load: a daemon's chart, a coloring page, chess pieces, a pasted picture. Since 0.2.0 a picture that arrived after the page was first drawn stayed hidden until the page was scrolled or zoomed, so a chart showed in the page's thumbnail and not on the page.
- The daemon's handwritten replies are set to the typed text's own measure: their lowercase as tall as a typed paragraph's, their lines 45 apart and 25 more between paragraphs, the first line where the next typed paragraph would sit. They were a quarter larger, with lines 58 apart.
- The retry box under a skipped or failed job's note is smaller (2.7 mm) and sits under the note's line at the left, still under the toolbar.
- Erasing a typed paragraph takes that paragraph only. Erasing the list item "milk" also cut the word out of every other paragraph holding it, the user's own request among them, which then stayed on the page.
- An Ink Adventure played on the page that asked for it keeps its story: the hero sheet goes on its own page. It landed on the story page, and the first turn wiped the story off. The story so far ends at a whole word.
- A month calendar with "on this day" cards draws for a month past the forecast; it failed and left the cards off.
- A habit tracker takes habits given by their names alone, and the model is told it can set the days.
- Deleting pages asks "Delete the selected page?" or "Delete the selected pages?", with no number that reads like a page's. Deleting every page of a notebook leaves it one blank page instead of refusing.
- Faster: a heavy page the engine has not read yet opens in a fifth of the time (1.24 s to 0.22 s for 150,000 strokes), sent to the editor a column per fact instead of a record per stroke. A large picture goes onto its page six times faster (13.3 s to 2.0 s for 29,538 strokes), the file the same to the byte. A web search no longer runs a test search first, and a job asking the same thing twice searches once. A week page fetches its seven days' history, not its month's.
- Fewer refused turns: a calendar asked for as "December 2026" or "the week starting Monday" is read, not refused, and one day's schedule is pointed to the agenda chart; a chart that names a place its plan does not have takes its step's own; a refused plan step is numbered as the model wrote it.

## 0.2.9

- Turning a selection with Alt works again. In 0.2.8, once a selection had been dragged and let go, pressing Alt (or Ctrl) put its strokes down in the middle of the next drag, so the turn left them where they were while the selection's frame turned, and the drop failed. A modifier key no longer puts a selection down, and nothing does in the middle of a drag. Moving, turning, turning with Alt, resizing, nudging and dragging twice now all land every stroke exactly where the selection's move puts it.
- Undo goes back one drag at a time while a selection is still selected: drag it, let go, drag it again, and Ctrl+Z puts it back where the first drag left it (Ctrl+Y forward again). Back where it started, the next Ctrl+Z undoes what came before it.
- Pressing a shape's number while drawing a shape changes the shape: begin a circle, press 4, and it is a square from the same first corner. The same for Select's loop and the zone eraser (2 to 5, and 1 back to a freehand loop).

## 0.2.8

- New page is instant after a heavy page. Making the blank page read every stroke of the page it follows, 13 seconds after a 150,000-stroke page; now it reads only the few blocks a blank page is made of (72 ms), the same file as before.
- The page you open after drawing on another opens a second sooner on an integrated card. Each page's editor compiled the graphics card's shaders again after any press on the page before (0.9 s); the window now keeps the card, and they stay compiled (4 ms).
- No more spinner over a page while it opens. The paper, template, typed text, pictures and the PDF's or book's page show as soon as the engine has said what the page is, which it does without reading the strokes (29 ms on a 150,000-stroke page); the strokes land as they come in. Clicks and keys still wait until they are in.
- A notebook opened again after you drew on it no longer waits for its page to be read again: the engine prepares the page as it saves it (reading it again took 1.9 s on a 150,000-stroke page; now 64 ms), and a page changed elsewhere in the notebook (a page added, deleted or moved) no longer makes every other page read again. Opened while it is still being saved, the page waits for the save and comes with what you drew last.
- A selection stays a picture until you let go of it. Let go after a drag, it stays where you dropped it as the picture; dragged again, it moves at once (4 ms to its first frame on a heavy page, a second before for a large selection). Anything else -- clicking away, Esc, another tool, a key, a zoom, saving, leaving the page -- puts its strokes down exactly first, one undo step for all its drags. While it is a picture its edges are a little softer than the strokes.
- Deleting pages from the grid works. The pages leave the grid at once and the rest are numbered anew; before, nothing changed, the notebook kept counting the deleted pages, and opening one said "there is no page 3". Pages deleted before this are cleaned up when the False Mirror starts. A notebook closed on a page that was then deleted opens on the nearest page left. Moving pages out of a notebook had the same fault and is fixed with it.
- A click with a pen makes a dot, with the mouse too.
- The ? by a document's name is only the shortcuts' button. It no longer turned into a spinner while a save took a moment or into ! when one failed; a failed save now says Not saved by the name, the reason on hover.

## 0.2.7

- Dragging a selection no longer draws the page again each frame. Picked up, the selection is drawn once as a picture, and the picture is moved, turned or resized, whatever the selection's size or the page's; let go, its strokes land exactly where it was let go. On an integrated card and a 150,000-stroke page, a frame of a drag takes the card 0.1 ms for 1,400 strokes and 0.4 ms for 32,000 (13 ms and 50 to 110 ms before); picking it up takes 8 ms and 94 ms, once. While it moves, how it blends with strokes under and over it is close, not exact; it is exact once let go.
- Letting go of a large selection that was only moved or turned no longer waits for its strokes' widths to be worked out again (90 ms for 84,000 strokes).
- A page shows at once and its strokes come in a frame at a time, in the page's order, as many as a frame holds; keys, clicks and the wheel wait until they are all in. The heaviest test page (150,000 strokes) shows in 0.23 s on the integrated card and has all its strokes in after 1.15 s (it showed nothing for 1.6 s before). Reading and making a page's strokes also cost less: its points in one array, each stroke's drawing data made in one walk along its points. The page once in is the same, pixel for pixel. A page the engine has not read since it changed still waits for the engine first.

## 0.2.6

- A notebook's title in the viewer opens its sheet: rename it, tag it, choose its cover (last page visited or first page) and export it. The gear by the title is gone. In the library, the bar for the documents picked (long or right click) has their cover as a dropdown. In the Mirror, renaming and the cover need Edit the Mirror on, and go to the tablet.
- Letting go of a large selection no longer freezes the page. Its strokes are made from what the graphics card already holds, a few at a time while the page keeps answering, and its save goes out in pieces. Undo and redo move the strokes back and forth on the card. On an integrated card, with 86,000 strokes of a 150,000-stroke page moved, the longest the page stopped answering was 35 ms letting go (830 ms before), 38 ms for the undo and 30 ms for the redo (240 to 330 ms before).
- Ctrl+Z pressed while a moved selection is still landing is no longer thrown away: the undo runs as soon as it lands.
- Undo after moving a selection no longer leaves pieces of it where it was moved. Strokes whose points changed in the move (often highlighters) came back drawn where the drag had left them, and stayed until the page was opened again.
- Removed the note under Renderer in Settings, and the one under a Mirror document's cover setting.
- A sketch is drawn on one grid. An icon drawn with a figure (a sun beside a house) is fitted with it, so it lands where it was put beside the other parts; it used to be placed on the page apart from the figure, and moved to the middle of the drawing when that fell outside (a sun on the house's window). A sketch never generates a picture: a picture that must look real is generated as its own step.

## 0.2.5

- Changing the graphics card, or between GPU and CPU, no longer closes and reopens the window. Jobs use the new choice at once, and the page editor from the next page you open: that page opens on the new card, in the same window, in about a second. Settings says so.
- Dragging a large selection on a heavy page no longer falls back to the processor: past about four million points it was moved there, a third of a second or more a frame (60 moves of most of a 150,000-stroke page took 27 seconds). It is moved on the graphics card now, whatever its size.
- A dragged selection is drawn where the pointer is. 0.2.4 drew it where the browser guessed the pointer would be next, which ran it ahead and pulled it back: dragging was jumpy.
- A notebook's settings, and a PDF's or a book's: the gear by its name in the viewer. Its cover shows the last page visited or the first page, as on the tablet. In the Mirror the setting is changed only with Edit the Mirror on, never over a change the tablet made first, and it is sent to the tablet.
- A page opened again opens faster: the engine keeps the last pages it prepared for the editor, until the page changes, so turning back to a page skips reading it again (a second or more on a 150,000-stroke page).
- A picture you ask to paste goes on the page as the picture itself, an image block like a coloring page, not pen strokes. A sketch is drawn from simple shapes; a picture generated, or found on the web, is still drawn in strokes you can erase and move. The model reads which from what you ask.
- Turning on Edit the Mirror shows a warning first, each time: editing the tablet's files with PaperDaemon raises the risk of damaging them. Canceling leaves it off.
- Covers show the page they should. A cover waiting to be drawn again was dropped when the library was painted anew (a sync landing, a notebook closed after reading it), so it kept its old page; and the False Mirror's covers were never drawn again once kept.

## 0.2.4

- Chess: the side you ask to play is the side you get. The model was told only "color" and read it as its own side.
- A page that passes its stroke limit moves whole pictures to the next page: a picture is no longer split between two pages.
- Pictures asked for together, like a gallery, are laid out two to a row.
- A game character's line is shown once a turn, never twice over.
- The first time it opens, PaperDaemon asks you to read its risks (RISKS.md, on GitHub) and acknowledge them, before anything else.
- Covers and page pictures are kept through updates and show at once, with no spinner. Only a picture whose page has changed since (written on here or on the tablet), or one never drawn, is drawn again: quietly, in the background, never while a page is open to edit, the old one shown until the new one takes its place. Updates used to throw every picture away, and each was then drawn one at a time while a spinner turned.
- The page a notebook opens at, and its card's "Page 5 of 9", follow what you read in PaperDaemon, in both mirrors, until the tablet opens another page of it. It is kept in PaperDaemon's own files; nothing of it goes to the tablet.
- Edit the Mirror, in Settings, off until you turn it on. Off, the Mirror's pages open to look at and PaperDaemon writes none of them; on, they open with the editor's tools as before. PaperDaemon cannot promise an edit never damages a notebook, above all after the tablet's software updates.
- A Mirror sync shows how far it has come: a thin bar under the viewer's bar while the document is open, along the top of its cover once it is closed.
- The arrow keys move what is selected a pixel of the screen a press, and on while held; the run is one step to undo. With nothing selected, Left and Right turn the page, Up and Down scroll a little, and Page Up and Page Down most of a screen.
- A settled selection shows what it is made of in icons to its right, reaching past the editor's frame where they need to: each brush's icon with its count of strokes. Click a brush to keep only its strokes; a selection of one brush shows the colors of its menu instead (a decomposed picture's colors counted with the nearest), and a click keeps only that color.
- A dragged selection is drawn where the pointer is about to be, so it keeps up with the pointer better, and lands exactly where it was let go. A selection over most of the view is moved by drawing the page whole each frame, which costs less there: on the integrated card, all of an ordinary page 5.4 ms a frame to 3.6, all of a 30,000-stroke page 43.7 to 35.1.

## 0.2.3

- With a graphics card chosen that no screen is connected to (an integrated card beside a discrete one), the page editor showed blank pages and empty boxes: the window was composed on the processor, and the editor's drawing never reached the screen. The window is composed on the screen's card again; the editor still draws on the card chosen.

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
- Daemon notes: the devil stands clear of the signature, and a line leaves exactly the signature's room. The traced signature is optional content (`content\signature
m_sig_daemon.json`); without it the name is lettered.

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
