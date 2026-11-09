## ADDED Requirements

### Requirement: A timeline takes dates
A timeline's events SHALL be placed by a date (an ISO date or month, or a date in words: a month and a day, with or
without a year, one with no year falling in the current year), by a year, or by a number, and each tick SHALL
say the day as a short date, the year, or the number given, unless the event names its own label. An event with none
of these SHALL be refused by name.

#### Scenario: A project timeline by dates
- **WHEN** the user asks for a timeline of five dated milestones from January to May
- **THEN** the five events stand along the line in date order, each with its day under it, on the first attempt
