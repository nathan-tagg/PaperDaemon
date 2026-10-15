# drawing/charts Specification

## Purpose
Turns data a job gathered into a crisp chart on the page, from a description the model writes, without
the model ever writing code.

## Requirements

### Requirement: The model gives data, not code
The chart tool SHALL take a chart type and data from the model, and SHALL refuse anything that is not a
supported chart type with data, saying what was wrong so the model can correct it.

#### Scenario: A malformed chart request
- **WHEN** the model sends a bar chart with no values
- **THEN** the tool refuses it with the reason, and the model's corrected request is drawn

### Requirement: Charts render offline
Charts SHALL render on this computer with no network access.

#### Scenario: Offline
- **WHEN** the computer is offline and a job draws a line chart
- **THEN** the chart renders as it does online

### Requirement: The data's order is kept
Categories, series and legend entries SHALL appear in the order the data gives them, never sorted
alphabetically unless the data asks for it.

#### Scenario: Months
- **WHEN** a bar chart's categories are Jan, Feb, Mar and Apr
- **THEN** the bars appear in that order

### Requirement: Charts reach the page as pictures that fill their box
A chart SHALL be placed on the page as a picture filling its planned box's full width, keeping its
aspect. A second chart planned into the same place SHALL replace the first.

#### Scenario: A chart below notes
- **WHEN** the host plans a large chart box below the user's notes
- **THEN** the chart picture spans that box's width

#### Scenario: A chart redrawn
- **WHEN** the model sends a corrected chart for the same place
- **THEN** only the corrected chart is on the page

### Requirement: Charts are legible on the tablet
Charts SHALL render in black, white and a few grays with crisp edges, with text in the tablet's
typeface or its substitute, and a chart with one series SHALL NOT come out inverted.

#### Scenario: One series
- **WHEN** a bar chart has a single series
- **THEN** its bars are outlined on a white ground, not white bars on a dark ground

### Requirement: Calendars are chart types
The chart tool SHALL draw a month calendar and a week view. Holidays and weather SHALL come from the
user's location setting, and a calendar too detailed to read on the page SHALL be filed as a document
with a pointer on the page.

#### Scenario: Next month
- **WHEN** a page asks for next month's calendar
- **THEN** a month calendar is made with the user's region's holidays, as a picture on the page or a
  document beside the inbox notebook when it would be too small to read
