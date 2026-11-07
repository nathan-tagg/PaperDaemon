## ADDED Requirements

### Requirement: A search's best pages are read for the question
A search step SHALL read the two best results' pages (not an encyclopedia's, whose lead comes its own way, and not
video or social sites) and give the step that writes the answer the parts of each that bear on the question: the
page's prose without its scripts, menus, headers, footers and forms, the paragraphs sharing the most of the question's
words, in the page's order, a short passage from each. A page that cannot be read SHALL leave its result as it was.
The model SHALL write the facts the results give, and say it could not find one they do not give.

#### Scenario: The next eclipse
- **WHEN** a page asks when the next total solar eclipse can be seen from the lower 48 states and which states are in
  its path, and a result's page says the 2044 path crosses Montana and North Dakota
- **THEN** the step that writes the answer is given that passage, and the answer names those states

#### Scenario: The internet is off
- **WHEN** network access is off in PaperDaemon's settings
- **THEN** no page is read, and the search step reports that search is unavailable

### Requirement: A search that finds nothing fails with the engines' reasons
A search that returns no results SHALL fail, with the reasons the search engines gave (asked too often, a CAPTCHA),
and the step that writes the answer SHALL be told to say it could not look the question up, never to write its facts
from memory.

#### Scenario: The engines refuse
- **WHEN** every engine of the search service refuses ("too many requests", "CAPTCHA") and a page asks a lookup
  question
- **THEN** the answer says it could not look it up just now, and the question stays on the page
