# Tasks

## 1. The rules

- [ ] 1.1 `concord/map.py`: twenty-eight shires with kinds, harbors, homes, polygons, labels and adjacency; a test that
      the adjacency is symmetric and connected, fleets reach every coast, polygons do not overlap
- [ ] 1.2 `concord/rules.py`: orders, resolution (cut supports, strength, stand-offs, head-to-head, no self-dislodgement,
      retreats by the engine, convoys), autumn harbors, builds and disbands, the win; `tests/test_concord_rules.py` on
      named positions (D3)
- [ ] 1.3 `concord/orders.py`: the user's orders from plain words (shire names by prefix and spelling, verbs and
      synonyms, build and disband), each line understood or shown back as not understood

## 2. The families

- [ ] 2.1 The six cast families chosen by their Concord rating and relationships; the user's family from the request
- [ ] 2.2 `concord/minds.py`: the order-writer (scores by harbor, threat, accord, nerve, read, ruthlessness; promises as
      constraints; seeded ties) and the accords; a test that every cast order is legal and that a kept promise binds

## 3. The letters

- [ ] 3.1 Letters read from the letters page by address; each family's answer in voice with `say`, `promise`, `keep`;
      promises recorded and bound; the unasked letter, once a season
- [ ] 3.2 Letters drawn on the letters page in the design, the user's left where written

## 4. The pages and the game

- [ ] 4.1 The map, orders, letters and log pages in the adventure's design, drawn again only when changed
- [ ] 4.2 State in the notepad (`game: "concord"`), `games.play` dispatch, the host's `concord` step; the request page
      becomes the map
- [ ] 4.3 A real game on the False Mirror: a season's orders read from handwriting, a letter answered in voice, a
      promise kept and one broken; then his tablet
