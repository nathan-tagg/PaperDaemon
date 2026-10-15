# Spec Delta

## Purpose

Turns a picture into pen strokes the tablet can show and the user can erase, faithful at the tablet's
resolution and cheap in strokes where it can be.

## ADDED Requirements

### Requirement: A picture becomes strokes in a box
The decomposer SHALL turn a picture into pen strokes that fill a given box on the page, keeping the
picture's aspect, and SHALL report the number of strokes it made.

#### Scenario: Decomposing a photo
- **WHEN** the decomposer is given a photo and a box
- **THEN** it returns strokes inside the box and their count

### Requirement: The same input gives the same strokes
The decomposer SHALL be deterministic: the same picture, box and settings SHALL give the same strokes.

#### Scenario: Running twice
- **WHEN** the same picture is decomposed twice into the same box
- **THEN** both runs give identical strokes

### Requirement: The decomposer ships frozen
PaperDaemon SHALL ship the decomposer engine exactly as the pipeline runs it today. A change to its output SHALL
need the maintainer's approval and a side-by-side comparison on real pictures.

#### Scenario: Porting
- **WHEN** the decomposer is ported to PaperDaemon
- **THEN** it gives the same strokes as the pipeline's engine on the same test pictures

### Requirement: No upsampling
The decomposer SHALL NOT enlarge a picture beyond its own resolution to fill a box, so thin lines are
not lost to interpolation.

#### Scenario: A small picture in a large box
- **WHEN** a small picture is decomposed into a large box
- **THEN** it is traced at its own resolution and its strokes are scaled to the box
