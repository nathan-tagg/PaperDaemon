## ADDED Requirements

### Requirement: The Concord of Merrow Bay is a game of letters resolved by the engine
PaperDaemon SHALL play the Concord of Merrow Bay from a request on a page: seven families hold the twenty-eight shires
of the bay, the user plays one and six of the cast play the others. Each season every family SHALL give one order to
each of its units -- hold, move, support a hold or a move, or convoy a militia by sea -- and the engine SHALL resolve
every order at once by the game's rules: a support cut by an attack from any shire but the one it is directed into, a
move won by the greater strength and stood off by an equal one, no family dislodging its own unit, a dislodged unit
retreated by the engine to the nearest shire that is free, a convoy broken when its fleet is dislodged. Nothing SHALL
move on a word alone: a promise of support counts only when the order is written. After each autumn every harbor SHALL
belong to the family standing in it, and each family SHALL build in its empty home harbors up to its harbors or disband
down to them. Eleven harbors SHALL win at the end of an autumn; after the tenth autumn the most harbors SHALL win, a
tie shared; a family with no harbor is out of the game.

#### Scenario: A supported attack
- **WHEN** the user's fleet moves on a shire held by one militia and the user's militia next to it supports the move,
  and no other order touches those shires
- **THEN** the militia is dislodged and retreats where the engine finds room, and the fleet stands in the shire

#### Scenario: A stand-off
- **WHEN** two families each move one unsupported unit into the same empty shire
- **THEN** neither moves, and the shire stays empty

#### Scenario: A support cut
- **WHEN** the unit giving a support is attacked from a third shire
- **THEN** the support does not count, whether or not the attack dislodges it

### Requirement: The user's orders are read from the orders page in plain words
The user SHALL write their orders on the orders page in plain words, one a line, naming shires by name ("Kettle Isle to
Gull Reach", "the Spit holds", "Ash Hill supports Kettle Isle to Gull Reach", "the Sound convoys Ash Hill to Pearl
Shoal", and with the autumn orders "build fleet at Harbor Row", "disband Fogwater"); a sync on that page SHALL resolve
the season. A line that cannot be read as an order SHALL be shown back as not understood and that unit SHALL hold.
After the season the orders page SHALL show every order of the user's as the engine read it, with its result, and a
fresh space to write.

#### Scenario: An order the reader got wrong
- **WHEN** the user wrote "Kettle Isle to Gull Reach" and the reader read a shire name that is no shire
- **THEN** the orders page shows that line as not understood, the fleet at Kettle Isle held, and the user can write
  it again next season

### Requirement: Letters are answered in the family's own voice, and weigh on the game
The user SHALL write letters on the letters page, each addressed to a family; a sync on that page SHALL deliver them
without advancing the season. Each family written to SHALL answer in its own voice, knowing its standing, its accord
with the writer and the orders it has already decided for the coming season, and MAY promise something (a support, no
attack, a shire left empty, a convoy); a promise the family means to keep SHALL bind its orders for the seasons named,
and a promise it means to break SHALL be broken by its orders and remembered against it when it comes out. A family
MAY write unasked, at most once a season, when it wants something or was attacked. Letters SHALL be drawn on the
letters page with the family's name and the season over each, the user's own letters among them as they were read,
their ink taken off the page once read, as the orders are.

#### Scenario: A promise kept
- **WHEN** Judge Shellby answers a letter with a promise to support the user's move into Fogwater next season and means
  it
- **THEN** his orders next season include that support, whatever else he does

#### Scenario: A promise broken
- **WHEN** a family promises no attack and means to break it
- **THEN** its orders next season may attack, and the game's record of that family's word to the user falls

### Requirement: The Concord's pages share the adventure's design
The game's pages SHALL be the map (the shires drawn as strokes from the game's own map data, harbors marked, every
unit a counter with its family's mark, the season and year under the title), the orders page, the letters pages and
the season log, in one column with one header and one type scale, no buttons and no counts, each drawn again only
when it changed. The families SHALL be told apart by marks and hatching, never by color alone.

#### Scenario: A new season
- **WHEN** a season resolves
- **THEN** the map is drawn again with every unit where it now stands, the orders page shows the user's orders as read
  and their results, and the log has a line for each family's season
