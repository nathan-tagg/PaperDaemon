## ADDED Requirements

### Requirement: Only a pure instruction comes off
The model SHALL rule as a question anything that asks something, also when it says how to answer or what to make of
the answer, and as a note the facts, numbers and lists a request works from. Only an instruction that asks nothing
(a request or a command) SHALL come off once it is carried out.

#### Scenario: A question that says how to answer
- **WHEN** the page asks "What were the main causes of the Dust Bowl? Answer in three short paragraphs." and a job
  answers it
- **THEN** the question stays above its answer

#### Scenario: The data a chart is made from
- **WHEN** the page holds "Electric bills this year: Jan $142, Feb $131, ..." and "Make a line chart of these", and
  the chart lands
- **THEN** the instruction is erased and the bills stay
