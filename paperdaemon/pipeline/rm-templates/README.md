# Templates the code needs, held as plain files

`blank-page.rm` is a real device page with its strokes and text stripped; every new page
the daemon writes starts as a copy of it. `notebook.content` is the `.content` a new
notebook is built from.

They are kept in the source tree rather than read out of the user's library. A template taken from a
document in the library would break page and notebook creation as soon as that document was deleted or
emptied from the trash, so nothing here depends on a document in the library.

They are inert data; nothing syncs them. In `notebook.content` the page entries are placeholders (the
code writes its own `cPages` entries) and the `cPages.uuids` author table is the part that is reused.
