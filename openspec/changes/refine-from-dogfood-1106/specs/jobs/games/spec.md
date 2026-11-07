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

### Requirement: The opponent stays at the table when the game ends
When a chess game ends -- a checkmate either way, a resignation, a draw of any kind -- the opponent SHALL stay on the
page and SHALL have the last word: a closing line in their own voice, true to how the game ended, with the table moving
their feelings with the result. When what they said on the move that ended the game was already theirs, that line
SHALL be the last word. Without a text model their face SHALL stay, in the mood the end left them in. A turn with no
line of the opponent's (a refused move, unclear writing) SHALL keep their face on the page, without its words.

#### Scenario: The player mates on their own move
- **WHEN** the player's move checkmates the opponent, who has no move to make
- **THEN** the opponent's face and a closing line of theirs are on the page with the final position

#### Scenario: A refused move
- **WHEN** the player moves a piece where it cannot go and it is put back
- **THEN** the opponent's face is still on the page

### Requirement: A finished game takes no more moves
A chess game that has ended SHALL refuse every further move, written or dragged, even when the final position still
has legal moves (after a resignation or an agreed draw); nothing moved after the end SHALL be no move at all, not a
refusal.

#### Scenario: A move written after a resignation
- **WHEN** the player resigned and a move is then written on the page
- **THEN** the move is not played and the finished game's record is unchanged

### Requirement: A draw offer is answered in the opponent's own voice
A chess opponent SHALL answer a draw offer in their own voice: taken, the game ends and their last word says so;
refused, they say why and the game goes on. A fixed line SHALL be the answer only when no text model can speak.

#### Scenario: A draw offered while the opponent is ahead
- **WHEN** the player writes "Draw?" and the opponent is ahead
- **THEN** the opponent refuses in their own words and the game goes on

### Requirement: A finished adventure says so
The last scene page of an ink adventure that is over (a victory, the hero's death, the hero fallen) SHALL say the
story has ended, and how, where the ideas for a next move would be; it SHALL offer no next move.

#### Scenario: The hero falls
- **WHEN** the hero drops to no hit points and the adventure ends
- **THEN** the scene page says "The end:" and that the hero has fallen, and shows no "You could:" ideas

### Requirement: A move that is not legal is refused out loud
A move the player writes or types that is read clearly but is not legal SHALL be refused: it SHALL come off the page,
the job's receipt SHALL name it, and the opponent SHALL tell the player in their own words. A piece moved where it
cannot go SHALL be put back and the opponent SHALL say so. A chess receipt SHALL never be empty, and SHALL say each
thing once.

#### Scenario: A king move two squares away
- **WHEN** the player types "Ke3" with their king on e1
- **THEN** nothing is played, "Ke3" comes off the page, the receipt says Ke3 is not a legal move here, and the
  opponent's line says so

### Requirement: A scene that did not change keeps its picture
An ink adventure turn in the same place where nothing in view changed (words were said, a look, a thought) and nobody
new came SHALL keep the last scene's picture as it was: no picture painted, and the card never handed to the picture
model, so the next job's text model is still loaded.

#### Scenario: Talking to someone in the same room
- **WHEN** the hero asks a question of someone already in the scene, in the same place
- **THEN** the scene keeps its picture, and the turn takes no picture time
