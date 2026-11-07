## ADDED Requirements

### Requirement: A written move is read from the player's ink, as written
The reader of a chess page SHALL be shown the player's ink alone: none of the page's pictures (the board, its pieces,
the opponent's words in the talk strip) and none of its typed text. It SHALL copy the handwriting, and a copy that is
a legal move in chess notation SHALL be played as written; only writing that is not notation ("knight takes c2")
SHALL be the reader's to translate into one of the legal moves.

#### Scenario: A pawn move a knight could also make
- **WHEN** the player writes "c3", and both the c-pawn and a knight can go to c3
- **THEN** the pawn moves to c3

#### Scenario: The opponent has just spoken
- **WHEN** the talk strip shows the opponent's last remark and the player writes their move under it
- **THEN** the player's move is read and played, and the remark is not taken for the player's words
