## ADDED Requirements

### Requirement: Trend and average lines are the host's
A line, step or bar chart SHALL take `trend: true` and `average: true`, and the host SHALL work those lines out from
the chart's own series (the least-squares line through each series in order; its mean) and draw them in the series'
ink, the trend dashed and the average dotted, each named at its right end. The model SHALL NOT type a trend or an
average as a series. The figures the host gives the words about a chart SHALL include the fitted trend.

#### Scenario: Bills with a trend line
- **WHEN** a job charts monthly bills of 142, 131, 118, 96, 88, 104, 139, 151 and 122 with a trend line
- **THEN** the trend line runs from about 119 to about 123, and the words beside the chart say it is going up

#### Scenario: A pie with a trend
- **WHEN** a pie chart's spec asks for a trend line
- **THEN** the spec is refused with the reason, and the model can change it

### Requirement: A chart's key never covers its data
A chart with a key (several series) SHALL show the key above the plot, in a row, never over the plot's marks.

#### Scenario: Two years of bills
- **WHEN** a bar chart shows this year's and last year's bills, January's bars the tallest
- **THEN** the key sits above the chart and every bar shows whole

### Requirement: A table entry stays in its cell
A table entry longer than its column at the table's type size SHALL go on two lines in its cell, broken at a space,
the two lines centered on the cell's middle; an entry that fits SHALL stay on one line.

#### Scenario: Eight columns of chores
- **WHEN** a chores table has a column per day and an entry "Set table, Recycling"
- **THEN** the cell shows "Set table," over "Recycling", whole, inside its borders

### Requirement: A week starts where it is asked to
A week calendar SHALL take `start` (YYYY-MM-DD) and run seven days from it; without one it SHALL run seven days from
today. The brief SHALL say so, and the job's first lines SHALL give the day this week began and the day next week
begins, by the user's first day of the week -- the host's date arithmetic, not the model's. A habit tracker SHALL
be a chart of type habit, not a calendar.

#### Scenario: Next week's appointments
- **WHEN** on a Saturday the user asks for a page for next week with a dentist on Monday and soccer on Saturday
- **THEN** the week runs from the first day of the user's next week, and soccer is on the coming Saturday, not today
