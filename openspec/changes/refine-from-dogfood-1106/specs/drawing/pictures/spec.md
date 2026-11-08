## ADDED Requirements

### Requirement: A sketch is shown back once for a fix
A sketch the host draws from shapes SHALL be shown back to the model once, on the page as it now stands, and the
model SHALL be allowed one fix: a part changed, the last thing taken back, or the figure drawn again; no call SHALL
mean it reads as the thing. With no look, "a lighthouse on a rock" came out as a few rectangles with no rock. A
second look SHALL NOT be taken by default: further rounds made drawings different rather than better.

#### Scenario: A part left out
- **WHEN** a sketch of a lighthouse on a rock is drawn without the rock
- **THEN** the model sees the page with the sketch on it, and may add the rock before the job commits
