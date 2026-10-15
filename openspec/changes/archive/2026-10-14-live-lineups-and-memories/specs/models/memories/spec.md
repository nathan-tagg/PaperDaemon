# Spec Delta

## ADDED Requirements

### Requirement: A lineup's memories
Each lineup SHALL keep memories: lessons its model learned about working for the user (complaints,
corrections, how the user wants something done). Memories SHALL NOT hold system-prompt material, the work on
a page, or personal data; a notebook's context belongs in its notepad. Every job of the lineup SHALL be shown
its memories, after the brief and before the user's prompts.

#### Scenario: Shown to the next job
- **WHEN** a lineup has the memory "erase my request when I write done"
- **THEN** every job of that lineup sees it, and jobs of other lineups do not

### Requirement: Only the model makes memories
The model SHALL add, replace and remove its lineup's memories through an optional `remember` list on its
decision, applied when the job ends and named in the job's record. A lineup SHALL keep at most 30; when it is
full, an added memory SHALL be refused and the model must replace one. The user SHALL be able to edit and
delete memories on the lineup's Memories tab, each card showing its text and the date saved, and SHALL NOT be
able to add one.

#### Scenario: Full
- **WHEN** a lineup keeps 30 memories and the model adds one
- **THEN** it is not kept, and the job's record says why

### Requirement: Memories follow their lineup
Renaming a lineup SHALL keep its memories; deleting a lineup SHALL delete them.

#### Scenario: Rename
- **WHEN** the user renames a lineup with memories
- **THEN** its Memories tab still lists them
