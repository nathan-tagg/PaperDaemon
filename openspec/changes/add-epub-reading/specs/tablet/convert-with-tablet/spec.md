# Spec Delta

## ADDED Requirements

### Requirement: The false mirror's books can be converted by the tablet
For a user with a real mirror, the false mirror's settings SHALL offer to convert its books with the tablet. Turning it
on SHALL warn that temporary books will appear in the root of the tablet's library and disappear, that a book is
converted only once a tablet is online, and that text may shift under ink already written on a book. With it on, a book
imported into the false mirror SHALL be uploaded to the root of the tablet's library with the configured ignore tag;
the daemon SHALL keep track of every book waiting; when the tablet's PDF of it arrives, PaperDaemon SHALL copy the PDF
and the reading settings into the false-mirror book and delete the tablet's copy outright.

#### Scenario: The tablet is off
- **WHEN** a book is imported into the false mirror while the tablet is off
- **THEN** the book is drawn from PaperDaemon's layout, and it is converted when the tablet next syncs

#### Scenario: The conversion lands
- **WHEN** the tablet's PDF of a waiting book reaches the real mirror
- **THEN** the false-mirror book gets the PDF, the copy in the tablet's library is deleted (not moved to the trash),
  and no job is started

#### Scenario: No real mirror
- **WHEN** a user has no real mirror
- **THEN** the setting is not shown
