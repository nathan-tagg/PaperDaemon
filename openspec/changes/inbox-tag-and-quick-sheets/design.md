# Design: inbox-tag-and-quick-sheets

## D1. Which notebooks are inboxes

Every live notebook in a library whose own tags include the inbox tag (Settings: tags.inbox, "inbox" by default,
matched without regard to case). A notebook in the trash, or in a folder in the trash, is not one. When a library has
none, its Quick sheets takes the page: the notebook named "Quick sheets" at the root of the library, as the tablet
keeps it (the newest, should there be two). Each mirror is looked at on its own: the Mirror's engine sends to the
Mirror's inboxes and the False Mirror's engine to its own.

## D2. Quick sheets in the False Mirror

The + menu's Quick sheets opens the library's Quick sheets on a new page at its end, with no name asked for; a
library without one gets one at its root.

## D3. The player's space on a game page

The tablet puts typed text below a picture on the page. The game page's picture ends at the top of the player's
space, and its last row carries the instruction, starting at the typed-text column's left edge. A turn reads the
page's typed text exactly, then the player's handwriting in the space through the vision model, and takes both off
once read.
