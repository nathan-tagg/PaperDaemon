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
