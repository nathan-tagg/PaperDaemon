# Spec Delta

## ADDED Requirements

### Requirement: The tablet's faces and templates come with an account
PaperDaemon SHALL use the faces and templates it takes from the reMarkable desktop app only while an account is signed
in. Without one, typed text and books SHALL be set in PaperDaemon's own faces and pages SHALL show no template; the
Template control SHALL say, on hover, to sign in to a reMarkable account to see and choose templates.

#### Scenario: No account
- **WHEN** a user without an account opens a false-mirror page whose file names a template
- **THEN** the page shows no template and the Template control's hover text asks them to sign in

### Requirement: Signing in warns about typed text
Adding an account SHALL warn that typed text in the false mirror may shift slightly, since it will then be set in the
tablet's faces.

#### Scenario: Adding an account
- **WHEN** a user with a false mirror adds an account
- **THEN** the warning is shown before the account is added

### Requirement: The false mirror can keep PaperDaemon's faces
The false mirror's settings SHALL offer to set its typed text and books in PaperDaemon's own faces even while an account
is signed in.

#### Scenario: Going back
- **WHEN** a signed-in user turns the setting on
- **THEN** false-mirror pages are drawn in PaperDaemon's own faces, and the real mirror is unchanged
