# drawing/text Specification

## Purpose
Writes the host's answers on the page as ink that lines up with the tablet's own typed text, so an
answer reads as part of the page.

## Requirements

### Requirement: Answers are ink in the tablet's typeface
The host SHALL write answers as ink strokes shaped and measured like the tablet's typed-text typeface,
and SHALL NOT insert them as typed text.

#### Scenario: A written answer
- **WHEN** a job answers a question in two sentences
- **THEN** the answer appears on the page as ink whose letters and line spacing match the tablet's typed text

### Requirement: Answers sit in the typed-text column
Answers SHALL be written in the page's typed-text column, wrapped to its width, starting below the
content they answer and clear of everything already on the page.

#### Scenario: An answer below a typed question
- **WHEN** the user typed a question at the top of a page
- **THEN** the answer starts on the next free line below it, aligned with the typed text's left edge

### Requirement: Bold is drawn
Words the answer marks as bold SHALL be drawn bold; other formatting marks SHALL NOT appear as symbols.

#### Scenario: An answer with a bold term
- **WHEN** the model's answer marks a term as bold
- **THEN** the term is drawn in heavier strokes and no asterisks appear on the page

### Requirement: The reMarkable fonts are never shipped
PaperDaemon SHALL NOT include the reMarkable app's font files. It SHALL use them from the user's own
reMarkable desktop app installation when present, and otherwise an openly licensed typeface with close
metrics.

#### Scenario: No desktop app installed
- **WHEN** the reMarkable desktop app is not installed
- **THEN** answers are drawn in the openly licensed substitute, still wrapped to the typed-text column
