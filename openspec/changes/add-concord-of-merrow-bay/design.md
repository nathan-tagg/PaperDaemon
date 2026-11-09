# Design: The Concord of Merrow Bay

## The game in one paragraph

Seven families hold the bay. Each season every family gives one order to each of its units: hold, move, support a
neighbor's hold or move, or carry a militia by sea. The engine resolves every order at once by the rules below, draws
the map again, and keeps the season's log. Harbors (twenty of the twenty-eight shires) are what counts: a family holds
a harbor by standing in it when autumn ends, builds a unit for each harbor it holds beyond its units, and loses units
when it holds fewer. A majority of the harbors (eleven) wins; when the tenth year ends, the most harbors wins. Nothing
moves on a word: a promise of support is kept only when the order is written. So the letters, which the model writes
for the cast and the user writes by hand, are the whole game.

## D1. The map (data, not a picture)

`concord/map.py`: twenty-eight shires, each `{id, name, kind: land | coast | sea, harbor: bool, home: family or None,
poly: [(x, y) ...] on the page's own grid, label: (x, y), neighbors: [ids], sea_neighbors: [ids]}`. The bay is a body
of water in the middle with six sea areas; islands and the shore hold the land and coast shires. Seven families have
two home harbors each (fourteen), six harbors are nobody's at the start (twenty in all). The adjacency is checked by a
test: symmetric, every shire reachable, a fleet can reach every coast from every sea in at most six moves, and no
polygon overlaps another. The map is drawn from this data every time (D6); there is no picture file.

Names, from the cast's own town: Merrow Point, the Strip, Tanglewood, the Works, Harbor Row, the Cannery, Kettle Isle,
Gull Reach, Lantern Spit, Fogwater, the Ferry Landing, Ash Hill, Salt Pans, Pearl Shoal, Drowned Bell (a sea), the
Narrows, the Sound, the Outer Banks, and ten more in the data.

## D2. The families

The user is one family (the request names one, or the engine gives them the Quills). The six others are cast members,
each the head of a family named after them, chosen for the game at the start from those rated at the Concord in
`catalog.json` (the ratings follow the cast's abilities: negotiation, bluff, read, ruthlessness, nerve). The shipped
six: Harriet Oakes (counts every vote first), Ottoline Graves (plays the player, never the board), Augustus Hale
(grasping, remembered), Bea Holloway (polite, and knows everything), Judge Shellby (by the rules, and a promise of his is kept),
Lenora Quill when the user is not a Quill, else Eben Stroud (patient, unreadable). A private cast pack may offer more;
the choice is by rating and by relationship (two who are enemies in their profiles are both taken when possible).

## D3. Orders and their resolution (`concord/rules.py`)

Units: a **fleet** stands on sea and coast shires and moves between them by water; a **militia** stands on land and
coast shires and moves overland, or by sea when fleets carry it (a chain of fleets on adjoining sea shires from one
coast to another). Orders, one a unit: `hold`; `move TO`; `support UNIT` (a hold) or `support UNIT to TO` (a move into
a shire adjacent to the supporter); `convoy MILITIA from A to B` (a fleet at sea). An order a unit cannot carry out is
a hold, and the log says why.

Resolution, all at once, the standard way with its two simplifications named:
1. A support is **cut** when the supporting unit is attacked from any shire other than the one its support is directed
   into. (Simplification: an attack by a convoyed militia cuts a support that targets its convoy's fleet all the same,
   so a convoy paradox never arises; the convoyed attack then fails if the convoy is disrupted.)
2. A unit's **strength** is one plus its uncut supports. A move succeeds when its strength beats the strength of every
   other unit moving into the same shire and, if the shire is held by a unit that does not leave, that unit's hold
   strength. Equal strengths **stand off**: nobody moves in, and a unit that stood off stays where it was.
3. Two units moving into each other's shires fight **head to head**: the stronger dislodges the weaker; equal, both
   stay. A unit moving out successfully leaves its shire to the strongest attacker.
4. No family dislodges its own unit, and a family's support never counts toward dislodging its own unit.
5. A **dislodged** unit retreats to an adjacent shire that is empty, was not fought over this season and is not where
   its attacker came from; the engine chooses for every family, nearest its own harbors first (simplification: no
   retreat phase; the log names where each dislodged unit went, or that it was disbanded with nowhere to go).
6. A **convoy** carries a militia when every fleet of its chain stands; a chain whose fleet is dislodged carries
   nothing, and the militia holds.

Seasons: spring and autumn take orders; after autumn every harbor is held by whoever stands in it, a family builds
one unit in each empty home harbor it holds for each harbor above its unit count (a fleet on a coast, a militia inland;
the user may write `build fleet at X` with the autumn orders), and disbands its units farthest from its harbors when
it holds fewer (the user may write `disband X`). A family with no harbor is out; its units leave the map. Eleven
harbors win at the end of any autumn; after the tenth autumn the most harbors win, a tie shared.

Every rule above has a test in `tests/test_concord_rules.py`, on named positions: a bounce, a supported attack, a cut
support, a head-to-head, a convoy and a disrupted convoy, a forbidden self-dislodgement, a retreat with one way out and
with none, builds and disbands, the eleven-harbor win.

## D4. The user's orders, read from the page

The orders page (D6) holds the user's writing space. A sync on it reads what was typed or written (inputarea, as the
adventure and chess read theirs), one order a line, in plain words: `Kettle Isle to Gull Reach`, `fleet at the Spit
holds`, `Ash Hill supports Kettle Isle to Gull Reach`, `the Sound convoys Ash Hill to Pearl Shoal`, `build fleet at
Harbor Row`. `concord/orders.py` parses each line: shire names by unique prefix or closest spelling (the names are the
vocabulary the reader is given), the unit at the shire named first is the one ordered, the verb from a short list with
its synonyms (`-`, `to`, `attacks`, `moves`; `holds`, `stays`; `supports`, `backs`; `convoys`, `carries`). A line the
parser cannot place is shown back as not understood, and that unit holds. The season resolves on that sync. The orders
page then shows last season's orders as the engine read them, each with its result, so a misread order is plain.

## D5. The letters

A sync on the letters page reads the user's writing: letters, each addressed (`To Harriet,` / `Harriet:` / `Dear Judge
Shellby`), the rest of the page's new writing to the last family addressed. For each family written to, the model is
asked as that character, with their persona, their standing (units, harbors, who attacked them), the season's position
in words, the engine's **accord** with the writer (D7), and their own orders for the coming season already written by
the order-writer (D7), to answer with `{say: the letter back, in their voice; promise: null or {kind: support | no_attack
| demilitarize | convoy, shire, unit, seasons}; keep: true or false}`. A promise the character means to keep becomes a
constraint on the order-writer for those seasons; one they mean to break is remembered as such, and the accord falls
when it comes out. Letters are drawn on the letters page in the one design, the family's name and the season over each,
the user's own letter among them as it was read (in italics), its ink taken off once read: the page stays a clean
record with room to write, as the orders page does.

A family also writes unasked when the order-writer wants something it cannot do alone (a support into a shire the user
borders) or when the user attacked it: one short letter a season at most, asking or warning, in voice.

## D6. The pages, in the adventure's design

The request page becomes the **map**: the shires drawn as strokes from the map data (coastlines and borders in pen,
names lettered, harbors marked with an anchor), each unit a counter with the family's mark (a letter: Q, O, G, H, B, S,
and the user's initial), fleets as boats and militias as towers, the season and year under the title. The **orders**
page follows: the user's orders of the season before as the engine read them with each one's result, then the writing
space. The **letters** page(s): every letter of the game so far, newest last, seven to a page, with room to write on
the last. The **seasons** page: every family's orders and what came of them, a season at a time, the newest seasons
that fit; retreats, harbors taken, builds and disbands under each autumn. Pages are redrawn only when their content changed (the map every season; the letters page when
a letter arrived). Everything is one column, header and hairline, no buttons, no counts, as the adventure's spec says.

## D7. The cast's orders (`concord/minds.py`)

Each cast family's orders come from an order-writer, not the model: deterministic given the seed, so a season is
reproducible and testable. For every unit it scores the candidate orders: taking an empty harbor (high), taking a
harbor from a family the accord is low with (high, scaled by ruthlessness), defending a threatened harbor (high),
supporting an ally's move (by accord and negotiation), moving toward the front (low). Nerve scales the taste for a
move that can bounce; read scales how well it foresees the others' likely moves (it runs the resolution on its guess of
their orders, one level deep); ruthlessness decides whether a low-accord ally's harbor is fair game. Promises kept
(D5) are constraints. The seed's dice break ties.

**Accord**: a number from -1 to 1 for every pair of families, starting from the profiles' relationships, raised by
support given and promises kept, lowered by attacks, dislodgements and promises broken. The user's accord with each
family is what their letters answer from, and what the order-writer treats them by.

## D8. State and dispatch

The game's state lives in the page's notepad like chess and the adventure (`CH.save_state`, `game: "concord"`): the
map's occupation, each family's units, harbors and home, the season and year, every order given and its result, every
letter, every promise, the accords, the seed. `games.play` dispatches a job on any of its pages to `concord.turn`
(the orders page resolves a season; the letters page delivers letters; the map and log pages take nothing). The host's
`concord` step starts it (steps.py GAMES, jobs.py GAME_START), from "start the Concord" and the like, as the adventure
and chess steps start theirs.

## D9. What is left out, on purpose

No retreat phase and no separate build phase for the user beyond the words `build` and `disband` with the autumn
orders (D3.5, D3); no cast-to-cast letters as text (their accords move by their deeds); no colors (the tablet's inks
are few: marks and hatching tell the families apart); no model in the rules (the engine resolves, the model only
speaks).
