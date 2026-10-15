# jobs/games Specification

## Purpose
A game is played on a page of its own, a turn per job. The model never holds the game: an engine keeps
its state and checks every move, and the model plays a character within the moves the engine allows.
Chess is the first.

## Requirements

### Requirement: Moves a request already makes are played first
When a request to play chess already makes moves ("I'm white. e4"), the model SHALL pass them in the game
step as a list of moves, in order from the start, as the user wrote them. The engine SHALL read each one
and check it by the rules, play the legal ones in order before the board is drawn, and stop at the first
it cannot read or that is not legal, saying so on the page. When it is then the opponent's turn, the
opponent SHALL reply. The model SHALL NOT hold the position or decide whether a move is legal.

#### Scenario: White opens with e4
- **WHEN** the request says "Let's play chess. I'm white. e4"
- **THEN** the board shows 1. e4, the opponent plays its reply, and the page says the e4 came from the
  request

#### Scenario: A move that is not legal
- **WHEN** the request's first move cannot be played from the starting position
- **THEN** nothing is played from the request, the page says which move was not played, and the game
  starts from the beginning

### Requirement: The chess board is as large as the page allows, with its coordinates inside it
A new chess page's board SHALL be as wide as the safe area allows once the opponent's talk strip and the
two rows of captured pieces have their height. The rank numbers SHALL sit inside the left column's
squares, each centered on its square's height, and the file letters inside the bottom row's squares,
each centered on its square's width, clear of the pieces, so nothing of the board sits outside it. The
opponent's portrait SHALL start at the board's left edge, and the name under it SHALL read clearly on
the tablet: large, bold and dark. The talk strip SHALL never be drawn so small it cannot be read: a face
that says and shows nothing is left out when the same speaker's face follows, and when the strip would
still shrink below a readable size, earlier speech is given as quoted lines instead of face rows, so no
words are lost. A game begun before this layout SHALL keep the board it was drawn with.

#### Scenario: A new game
- **WHEN** a chess game starts on a new page
- **THEN** the board spans nearly the safe area's width, its coordinates are inside its edge squares, and
  the opponent's face lines up with the board's left edge
