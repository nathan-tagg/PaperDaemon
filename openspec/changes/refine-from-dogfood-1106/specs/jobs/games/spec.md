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
The last scene page of an ink adventure that is over (a victory, or a story that ended with its hero's death before
death saves) SHALL say the story has ended, and how, where the ideas for a next move would be; it SHALL offer no next
move.

#### Scenario: A victory
- **WHEN** the hero wins and the adventure ends
- **THEN** the scene page says "The end: a victory." and shows no "You could:" ideas

### Requirement: A hero at no hit points makes death saves
An ink adventure's hero who drops to 0 hit points, or is struck down, SHALL be dying, not dead: the scene page SHALL
say so, with the death saves failed so far, and SHALL offer two things to do: roll a death save, or give up. A death
save SHALL be a d20 the engine rolls, 10 or more a success. One success SHALL get the hero back up with 1 hit point;
the third failure, or giving up, SHALL be the hero's death. On a failed save the story's hit points for that turn
SHALL NOT be taken: the dice decide (a failure and "+1 hit point" at once got a hero up with no success). The model
SHALL read whether the player rolls or gives up; anything but giving up SHALL be a roll.

#### Scenario: A death save that succeeds
- **WHEN** the hero lies dying and the player writes "roll", and the engine rolls 14
- **THEN** the hero gets back up with 1 hit point and the story goes on from there

#### Scenario: The third failure
- **WHEN** the hero has failed two death saves and the engine rolls 4
- **THEN** the hero dies

### Requirement: A death does not end the adventure
When the hero dies, the adventure SHALL go on, as the model tells it: in the great beyond, the hero back years later
as something else, a successor taking up what the hero left behind, or any other way true to the story. A successor
SHALL be a new hero the engine makes from the model's proposal, the fallen hero kept in the story's record; a hero
who goes on themselves SHALL have their hit points whole again.

#### Scenario: The hero dies
- **WHEN** the hero's third death save fails
- **THEN** the scene page tells the death and what comes after it, offers what to do next, and the next turn goes on
  with whoever the story now follows

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

### Requirement: Talk after a match goes to the opponent
On the page of a chess game that is over, what the player writes or types to the opponent SHALL go to the opponent:
it SHALL come off the page, and the opponent SHALL answer in their own voice, the table deciding as on any turn, their
face kept when they say nothing. Anything else written there (a new game, a request, notes of the player's own) SHALL
be no business of the game's: the page's job SHALL be any page's. The model SHALL tell which it is; no words are
matched.

The words the opponent answers SHALL be the player's own, as typed or as the reader copied the handwriting; the
model SHALL only say whether they are said to the opponent (a reader asked for the words put words nobody wrote in
place of a request, and the opponent answered them).

#### Scenario: A word after the game
- **WHEN** the player writes "Good game!" under a finished game
- **THEN** the writing comes off and the opponent answers it on the page

#### Scenario: A new game asked for on a finished game's page
- **WHEN** the player writes "start a new game against someone stronger" under a finished game
- **THEN** the writing is not the old game's, and the page's job goes on as any page's

### Requirement: A strong opponent takes no draw in the opening
A chess opponent of 1600 or stronger SHALL refuse a draw offered in the first 20 moves unless it stands clearly
worse, and SHALL say why in its own voice. A 2600 took a draw on move 3 of an even game.

#### Scenario: A draw offered on move 3
- **WHEN** the player offers a draw on move 3 of an even game against a 2600
- **THEN** the opponent refuses, saying the game has barely begun, and the game goes on

### Requirement: Every group text gets an answer
Every member of a group text SHALL have the chance to answer a message, and none SHALL have to; when the dice let
nobody speak, the member the message names first, else the most talkative, SHALL answer, and the next when that one
says nothing, so that every message gets at least one reply.

#### Scenario: A greeting to two
- **WHEN** the player texts "Hi both!" to a group of two and neither would speak on their own
- **THEN** one of them answers
