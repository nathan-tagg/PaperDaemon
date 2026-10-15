# Spec Delta

## ADDED Requirements

### Requirement: The app build compiles the decomposer first
Building the desktop app SHALL first compile the C decomposer: for any x86-64 processor when the build is
to be shared or published, for the building machine's processor otherwise. A failed compile SHALL stop the
build.

#### Scenario: A compile error
- **WHEN** the C decomposer fails to compile
- **THEN** no app is built, and the build's error names the compile step

#### Scenario: A shared build
- **WHEN** the app is built to be shared
- **THEN** its decomposer library runs on an x86-64 processor other than the building machine's

### Requirement: The app ships only what it runs
Once nothing the app runs imports them, the packaged app SHALL NOT include the decomposer's Python
reference dependencies (OpenCV, numba with llvmlite, SciPy, scikit-image, Shapely). They SHALL stay
pinned, at the exact versions the reference's results depend on, in a test-only dependency group.

#### Scenario: A built app
- **WHEN** the app is built
- **THEN** its folder holds none of those packages, and a picture sent from the desktop still becomes
  strokes
