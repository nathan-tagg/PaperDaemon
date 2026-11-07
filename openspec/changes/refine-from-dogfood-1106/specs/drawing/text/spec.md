## ADDED Requirements

### Requirement: Fractions and signs are lettered as themselves
The lettering SHALL draw fractions (½ ¾ ⅛ and the rest) as one glyph each, a small numerator over a slash over a small
denominator; superscript and subscript digits small and raised or lowered; and ≈ ± × ÷ √ ∞ π µ as those signs, all
from the installed face's own strokes. A line holding none of them SHALL keep the baseline it always had.

#### Scenario: A recipe's time
- **WHEN** an answer says "Bake 6½–7 minutes"
- **THEN** the page shows six and a half, not "61/2"

#### Scenario: About forty minutes
- **WHEN** an answer says "≈ 40 minutes"
- **THEN** the sign is drawn before the number

### Requirement: A typewriter's dash is drawn as a dash
A typewriter's dash between words (" -- ") in the words the host letters SHALL be drawn as a dash, not as two hyphens.

#### Scenario: An aside in an answer
- **WHEN** an answer says "the sweet spot -- cool enough to slow mold"
- **THEN** the page shows a dash between "spot" and "cool"

### Requirement: A number keeps its unit
The lettering's line wrap SHALL keep a number and the short word after it ("3 pm", "10 kg") on one line.

#### Scenario: A time at the end of a line
- **WHEN** "...November 19 at 3 pm." wraps with "3" the last word that fits on a line
- **THEN** "3 pm." starts the next line together
