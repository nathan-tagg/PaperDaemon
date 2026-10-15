# Security

Please report a vulnerability privately through GitHub's **Report a vulnerability** (the repository's
Security tab), not in a public issue.

What PaperDaemon protects:

- **Your reMarkable login.** Kept only in Windows' Credential Manager, never in a file or a log, and sent only
  to reMarkable's own cloud.
- **API keys and the pairing token.** Kept in Credential Manager as well. The engine listens on `127.0.0.1`,
  this computer only, and every request must carry the pairing token.
- **Your library.** PaperDaemon never permanently deletes anything in your reMarkable cloud: moving a document
  to the trash is the furthest it goes.
- **Updates.** Checked only when you ask, and installed only when you choose to and the update's signature
  matches the key built into the app. The installer itself is not code-signed.
- **Uninstalling.** Removes everything PaperDaemon stored on the computer, including its Credential Manager
  entries, and nothing else.
