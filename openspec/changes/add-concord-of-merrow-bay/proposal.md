# Proposal: add-concord-of-merrow-bay

## Why

The maintainer asked for more games on the tablet: "monopoly, risk, diplomacy, catan, more". Of the four,
a game of negotiation fits a pen tablet best: the tablet is for writing letters, and the cast of Merrow Bay already has
voices, agendas, secrets and tells written for exactly this. The engine owns the rules, the dice-free resolution and
the map; the model owns the letters.

## What Changes

- A new game, **The Concord of Merrow Bay**, started like chess and the Ink Adventure from a request on a page ("start
  the Concord", "a game of the Concord as the Quills"). Seven old families hold the shires of the bay; the user plays
  one, six of the cast play the others. Each season every family writes orders for its fleets and militias (hold,
  move, support, convoy); all orders resolve at once by the engine's rules, so nothing moves on a word alone and the
  only way to get help is to be believed.
- The whole game is letters. The user writes to a family on the letters page; the engine reads the letter, and the
  family answers in its own voice, keeps or breaks its word by character, and writes its own letters when it wants
  something. The cast's orders are the engine's (an order-writer with the character's temperament: cautious, grasping,
  loyal, treacherous), told to the model before it writes, so a promise in a letter and the orders that follow it
  agree or disagree on purpose.
- The pages, in the one design the adventure's pages have: the map (shires drawn by the engine, each family's units
  as counters), this season's orders (the user writes theirs there; the last season's are shown back as the engine
  read them), the letters (the user's and the families'), and the season log. Every page is drawn again only when it
  changed.
- Victory at a majority of the bay's harbors, or the most harbors when the tenth year ends; a family with no harbor
  left is out, its letters answered no more.

## Impact

- Affected specs: jobs/games (the game, its orders, its letters, its pages: requirements added).
- Code: `paperdaemon/pipeline/games/concord/` (the map data, the rules and resolution, the order-writer, the pages,
  the letters), `paperdaemon/pipeline/games/__init__.py` (dispatch), `paperdaemon/pipeline/host/steps.py` and
  `jobs.py` (the `concord` step), the cast's game ratings (`catalog.json`: concord).
- Needs a real game on the False Mirror before release (a season's orders read from handwriting; a letter answered in
  voice), then his tablet.
