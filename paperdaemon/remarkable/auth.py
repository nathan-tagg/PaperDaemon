"""The reMarkable device token, and the short-lived user token minted from it.

The DEVICE token is long-lived and is effectively a password to the whole reMarkable account. It is
pasted into PaperDaemon's settings (see the README for how to get one) and kept in the OS credential
store. It is never logged and never shown back in full.

The USER token lasts a few hours. It is minted once, reused from memory, and renewed a few minutes
before it expires or as soon as the server answers 401.
"""
import base64
import json
import time
import urllib.error
import urllib.request

from .. import vault

AUTH = "webapp-prod.cloud.remarkable.engineering"
DEVICE_KEY = "remarkable-device-token"

_TOKEN = {"jwt": None, "exp": 0.0}


class NotConnected(RuntimeError):
    """No device token has been set, or the cloud refused it."""


def device_token():
    t = vault.get(DEVICE_KEY)
    if not t:
        raise NotConnected("no reMarkable device token is set -- add one in Settings > Tablet")
    return t


def set_device_token(token):
    """Store a pasted token. The desktop app's registry value comes wrapped as @ByteArray(...)."""
    t = (token or "").strip()
    if t.startswith("@ByteArray(") and t.endswith(")"):
        t = t[len("@ByteArray("):-1]
    vault.put(DEVICE_KEY, t)
    forget_user_token()


def forget_user_token():
    _TOKEN["jwt"], _TOKEN["exp"] = None, 0.0


def claims(jwt):
    """The (unverified) claims of a JWT, for display and expiry only."""
    try:
        body = jwt.split(".")[1]
        body += "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(body))
    except Exception:
        return {}


def user_token(force=False):
    if not force and _TOKEN["jwt"] and time.time() < _TOKEN["exp"] - 300:
        return _TOKEN["jwt"]
    r = urllib.request.Request("https://%s/token/json/2/user/new" % AUTH, method="POST")
    r.add_header("Authorization", "Bearer " + device_token())
    try:
        jwt = urllib.request.urlopen(r, timeout=25).read().decode().strip()
    except urllib.error.HTTPError as ex:
        if ex.code in (400, 401, 403):
            raise NotConnected("the reMarkable cloud refused the device token (%d)" % ex.code)
        raise
    _TOKEN["jwt"] = jwt
    _TOKEN["exp"] = float(claims(jwt).get("exp", 0))
    return jwt


def describe():
    """What the settings page shows about the connection -- never the token itself."""
    if not vault.has(DEVICE_KEY):
        return {"set": False}
    c = claims(device_token())
    return {"set": True, "device": c.get("device-desc") or c.get("device_desc"),
            "device_id": c.get("device-id") or c.get("device_id")}
