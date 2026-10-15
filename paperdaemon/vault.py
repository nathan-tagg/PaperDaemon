"""Secrets live in Windows Credential Manager -- never in settings.json, never in a log.

Every entry is under the service "PaperDaemon" (PAPERDAEMON_SERVICE names another, for a test install).
Names in use:
    remarkable-device-token     the reMarkable login the cloud client signs in with
    pairing-token               what every client of PaperDaemon's API must present
    key:<role>:<where>          an API key for one server or service: key:text:api.anthropic.com,
                                key:image:api.openai.com, key:search:brave. Lineups that use the same one share
                                its key; lineups that use different ones never overwrite each other's.
    key-index                   the names of the key:<role>:<where> entries (names only), so the uninstaller can
                                remove every one
"""
import json
import os
import urllib.parse

import keyring
import keyring.errors

SERVICE = os.environ.get("PAPERDAEMON_SERVICE") or "PaperDaemon"
NAMES = ("remarkable-device-token", "pairing-token")
INDEX = "key-index"


def key_name(role, where):
    """The entry an API key is kept under: `role` text, image or search; `where` the server's address (its host
    name is used) or the search service's name."""
    w = str(where or "").strip()
    if "://" in w:
        w = urllib.parse.urlsplit(w).hostname or w
    return "key:%s:%s" % (role, w.lower() or "default")


def get(name):
    try:
        return keyring.get_password(SERVICE, name)
    except keyring.errors.KeyringError:
        return None


def _index():
    try:
        return [n for n in json.loads(get(INDEX) or "[]") if isinstance(n, str)]
    except ValueError:
        return []


def _set_index(names):
    names = sorted(set(names))
    if names:
        keyring.set_password(SERVICE, INDEX, json.dumps(names))
    else:
        try:
            keyring.delete_password(SERVICE, INDEX)
        except keyring.errors.PasswordDeleteError:
            pass


def put(name, value):
    value = (value or "").strip()
    if not value:
        return delete(name)
    keyring.set_password(SERVICE, name, value)
    if name.count(":") >= 2:
        _set_index(_index() + [name])


def delete(name):
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass
    if name in _index():
        _set_index([n for n in _index() if n != name])


def has(name):
    return bool(get(name))


def keys():
    """The key:<role>:<where> entries that hold a key (names only)."""
    return [n for n in _index() if has(n)]


def forget_all():
    """Delete every entry PaperDaemon keeps, by its exact name (the uninstaller's cleanup). -> the names that
    were there."""
    gone = []
    for name in list(NAMES) + _index():
        if get(name):
            delete(name)
            gone.append(name)
    try:
        keyring.delete_password(SERVICE, INDEX)
    except keyring.errors.PasswordDeleteError:
        pass
    return gone
