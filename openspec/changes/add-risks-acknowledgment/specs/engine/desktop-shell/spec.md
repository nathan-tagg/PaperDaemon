## ADDED Requirements

### Requirement: The risks are acknowledged before anything else
Until the setting `risks.acknowledged` is on, the window SHALL show, before setup or any screen, a dialog that cannot
be dismissed. It SHALL ask the user to read PaperDaemon's risks and acknowledge them, link RISKS.md on GitHub (opened
in the user's browser), and say that PaperDaemon is a third-party application, not made or endorsed by reMarkable,
meant to make an unmodified reMarkable tablet more useful, and that its author is not responsible for what anyone
does with it or for any loss or damage it causes. Acknowledging SHALL save the setting and carry on to setup or the
screens; once the setting is on, the dialog SHALL NOT show again.

#### Scenario: The first open
- **WHEN** PaperDaemon's window opens and the risks have not been acknowledged
- **THEN** the risks dialog is all it shows, and Esc does not close it

#### Scenario: Acknowledged
- **WHEN** the user presses "I acknowledge the risks"
- **THEN** the setting is saved, the window carries on, and the dialog does not show when the window opens again
