"""The reMarkable sync client: PaperDaemon's own route to the library, no desktop app involved. The engine,
the daemon and the host all use this one module.

PULL brings PaperDaemon's mirror up to date with the cloud. PUSH sends pages PaperDaemon wrote back up,
so they appear on the tablet. The NOTIFIER holds the push channel that says the moment something
changed, so the mirror keeper pulls on change instead of polling.

The store is CONTENT-ADDRESSED and IMMUTABLE: uploading a blob never overwrites one, and the root pointer
moves only by compare-and-swap on the library's generation, so a write never lands over a change it did not see.

Storage layout (sync 1.5): the root pointer names a root index (root.docSchema) listing one line per
document, "hash:flags:uuid:count:size"; each document's index (<uuid>.docSchema) lists its files the
same way. Leaf hashes are sha256 of the bytes; an index's hash is sha256 over its children's raw
hashes, in file order.
"""
import base64
import hashlib
import http.client
import json
import os
import random
import re
import struct
import sys
import time

from .. import paths
from .auth import user_token

SYNC = "internal.cloud.remarkable.com"

# The engine's own folders; the daemon and the host are pointed at theirs (the same ones, or the benchmark's
# isolated copies) through RM_MIRROR and RM_STATE.
MIRROR = os.environ.get("RM_MIRROR") or paths.mirror_dir()
SAFETY = os.path.join(os.environ["RM_STATE"], "cloud-safety") if os.environ.get("RM_STATE") else paths.safety_dir()
STATE = os.path.join(SAFETY, "mirror-state.json")

# what the mirror keeps: everything the cloud has for a document except thumbnails. A page's picture
# lives at <doc>/<page>/<asset>.png and its .rm only references it, so assets come too; a PDF or
# EPUB is the document itself, so its source file comes too.
WANT = (".rm", ".content", ".metadata", ".pagedata", ".pdf", ".epub", ".epubindex",
        ".png", ".jpg", ".jpeg", ".template")
# A TEMPLATE (rM Methods) is a document of its own whose .template file holds its drawing; kept since 0.1.32. When what
# the mirror keeps grows, the next pull revisits the documents a new kind belongs to, once, though the cloud did not
# change them: the template documents pulled before .template was kept.
WANT_KEY = ",".join(WANT)


def _is_template(uuid):
    try:
        with open(os.path.join(MIRROR, uuid + ".metadata"), encoding="utf-8") as f:
            return json.load(f).get("type") == "TemplateType"
    except (OSError, ValueError):
        return False

# the server's own hint of how long a user token is good for, in seconds
TTL_HINT = {"seconds": None}


class CloudBusy(Exception):
    """Rate limited, or the service is briefly unavailable. Back off; do not retry hard."""


# ------------------------------------------------------------------- files
def replace(tmp, dest):
    """os.replace that waits out another process's moment with either file (up to 2 s) -- a
    reader parsing the page, or a virus scanner on the copy just written."""
    for i in range(40):
        try:
            return os.replace(tmp, dest)
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def content(doc):
    """A document's .content from the mirror, or {}."""
    try:
        with open(os.path.join(MIRROR, doc + ".content"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def live_pages(c):
    """The pages a .content lists that are not deleted, in the app's order (by their keys), each as {id, redir?: {value}}.

    A document last saved by older software (formatVersion 1) has no `cPages`: it lists its page ids in `pages`
    and each page's source page in `redirectionPageMap` (-1 for a sheet inserted between them). Those are read
    into the same shape."""
    if "cPages" in c or not isinstance(c.get("pages"), list):
        live = [p for p in c.get("cPages", {}).get("pages", []) if "deleted" not in p]
        # the app shows pages in the order of their keys, and stores them in that order too; a list written out of
        # order (an entry appended for a page inserted in the middle) is still shown by key
        if all(isinstance((p.get("idx") or {}).get("value"), str) for p in live):
            live.sort(key=lambda p: p["idx"]["value"])
        return live
    redir = c.get("redirectionPageMap") or []
    out = []
    for i, pid in enumerate(c["pages"]):
        p = {"id": pid}
        if i < len(redir) and isinstance(redir[i], int) and redir[i] >= 0:
            p["redir"] = {"value": redir[i]}
        out.append(p)
    return out


# ------------------------------------------------------------------- transport
class LocalOnly(RuntimeError):
    """A cloud call from a process working the false mirror: a bug, never a request to send."""


def _call(method, path, token, filename=None, body=None, ctype=None, tries=3):
    if paths.local_only():
        # THE FALSE MIRROR NEVER REACHES THE CLOUD: every request to it goes through here, and none is made
        raise LocalOnly("the false mirror never reaches the cloud (%s %s)" % (method, path))
    last = None
    for _ in range(tries):
        try:
            c = http.client.HTTPSConnection(SYNC, timeout=60)
            h = {"authorization": "Bearer " + token}
            if filename:
                h["rm-filename"] = filename
            if ctype:
                h["content-type"] = ctype
            c.request(method, path, body=body, headers=h)
            r = c.getresponse()
            hint = r.getheader("rm-token-ttl-hint")
            if hint:
                try:
                    TTL_HINT["seconds"] = int(hint)
                except ValueError:
                    pass
            out = (r.status, r.read())
            c.close()
            return out
        except Exception as e:                      # transient TLS/read timeouts
            last = e
    raise last


_CRC_TABLE = None


def crc32c(data):
    """Castagnoli CRC32C (zlib.crc32 is the IEEE polynomial -- the wrong one). Blob uploads are
    refused with 400 "missing checksum" without it: `x-goog-hash: crc32c=<base64 big-endian>`."""
    global _CRC_TABLE
    if _CRC_TABLE is None:
        poly, tbl = 0x82F63B78, []
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ (poly if c & 1 else 0)
            tbl.append(c)
        _CRC_TABLE = tbl
    crc = 0xFFFFFFFF
    for b in data:
        crc = _CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def goog_hash(data):
    return "crc32c=" + base64.b64encode(struct.pack(">I", crc32c(data))).decode()


def put_blob(token, data, filename, hash=None):
    """Upload one blob, addressed by its hash. A LEAF's hash is sha256 of its bytes; an INDEX's
    (.docSchema) is the merkle hash over its children, which must be passed explicitly -- the server
    answers the content hash with 400 "invalid hash". A burst of uploads draws 429s, so a busy
    answer backs off (doubling, five times) rather than failing the whole push."""
    if paths.local_only():
        raise LocalOnly("the false mirror never reaches the cloud (upload %s)" % filename)
    h = hash or hashlib.sha256(data).hexdigest()
    hd = {"authorization": "Bearer " + token, "rm-filename": filename,
          "x-goog-hash": goog_hash(data)}
    if filename == "root.docSchema":
        hd["content-type"] = "text/plain; charset=UTF-8"
    out = None
    for attempt in range(6):
        c = http.client.HTTPSConnection(SYNC, timeout=60)
        c.request("PUT", "/sync/v3/files/" + h, body=data, headers=hd)
        r = c.getresponse()
        out = (r.status, r.read(), h)
        c.close()
        if out[0] not in (429, 500, 502, 503, 504) or attempt == 5:
            break
        time.sleep(2.0 * (2 ** attempt))
    return out


def get_root(token=None, _retry=True):
    """(hash, generation). Looks at the status before the body: any error raises with what it was."""
    token = token or user_token()
    st, b = _call("GET", "/sync/v4/root", token)
    if st == 200:
        d = json.loads(b)
        return d["hash"], d["generation"]
    if st == 401 and _retry:
        return get_root(user_token(force=True), _retry=False)   # the user token went stale
    if st in (429, 500, 502, 503, 504):
        raise CloudBusy("%s %s" % (st, b[:120].decode("utf-8", "replace")))
    raise RuntimeError("GET /sync/v4/root -> %s %s" % (st, b[:160].decode("utf-8", "replace")))


def get_blob(token, h, filename):
    st, b = _call("GET", "/sync/v3/files/" + h, token, filename)
    if st in (429, 500, 502, 503, 504):
        raise CloudBusy("blob %s: %s" % (filename.split("/")[-1], st))
    if st != 200:
        raise RuntimeError("blob %s (%s): %s %s" % (h[:12], filename, st, b[:120]))
    return b


def index_hash(child_hashes):
    """sha256 over the children's RAW hash bytes, in file order."""
    return hashlib.sha256(b"".join(bytes.fromhex(c) for c in child_hashes)).hexdigest()


def put_root(token, h, generation, broadcast=True):
    """Move the root pointer -- the one destructive call. `generation` is a compare-and-swap: if
    anything else moved the root since it was read, the server refuses."""
    body = json.dumps({"broadcast": broadcast, "hash": h, "generation": generation}).encode()
    return _call("PUT", "/sync/v3/root", token, "roothash", body, "application/json")


def in_trash(uuid, parents):
    """True when the item, or any folder above it, is in the trash. `parents` maps uuid -> parent."""
    seen = set()
    while uuid and uuid not in seen:
        seen.add(uuid)
        parent = parents.get(uuid)
        if parent == "trash":
            return True
        uuid = parent
    return False


def library(token=None, mirror=None):
    """[(uuid, visibleName, type, parent)] from the mirror -- what PaperDaemon knows about. Whatever is in
    the trash, directly or inside a trashed folder, is gone for every part of PaperDaemon and is not listed."""
    mirror = mirror or MIRROR
    items = []
    for fn in os.listdir(mirror):
        if fn.endswith(".metadata"):
            try:
                with open(os.path.join(mirror, fn), encoding="utf-8") as f:
                    m = json.load(f)
            except (OSError, ValueError):
                continue
            items.append((fn[:-len(".metadata")], m.get("visibleName"), m.get("type"), m.get("parent")))
    parents = {u: p for u, _, _, p in items}
    return [it for it in items if not in_trash(it[0], parents)]


# ---------------------------------------------------------------- push channel
# The cloud says when something changed: wss://<notifications host>/notifications/ws/json/1, an
# ordinary HTTP/1.1 upgrade with the user token as a bearer header. The server allows ONE
# connection per DEVICE -- a second client signed in with the same device token takes the slot and
# the first is dropped within a second, with no frame and no reason. A device token of PaperDaemon's own
# gives it its own slot.
#
# A message names the device that caused it, so our own pushes can be told apart:
#   {"message":{"attributes":{"event":"SyncComplete","sourceDeviceID":"...", ...}}}
# It says THAT something changed, never what, so a pull still follows -- one request per real change.
NOTIFY_PATH = "/notifications/ws/json/1"
CRLF = "\r\n"
# a connection that lived this long is healthy and resets the reconnect backoff: longer than the
# instant close another client of the same device causes, shorter than any real quiet period
HEALTHY_AFTER = 30.0
# after this long with nothing received the connection pings, and a ping unanswered this long means the network is
# gone (measured: the server answers in under 0.2 s)
PING_AFTER = 20.0
PONG_WAIT = 10.0


# THE TABLETS AN ACCOUNT HAS, AS THE SERVICE SHOWS THEM: one library for every device, and a change notification
# that names the device it came from (sourceDeviceID, sourceDeviceDesc -- "remarkable" for a tablet -- and a name when
# the message carries one). Kept as they are seen, in <state>/devices-seen.json, so how several tablets of one
# account look is read off real messages rather than guessed.
def note_device(attrs):
    try:
        path = os.path.join(paths.state_dir(), "devices-seen.json")
        try:
            with open(path, encoding="utf-8") as f:
                seen = json.load(f)
        except (OSError, ValueError):
            seen = {}
        d = seen.setdefault(str(attrs.get("sourceDeviceID")), {"first": int(time.time()), "events": 0})
        d.update(desc=attrs.get("sourceDeviceDesc") or d.get("desc"), last=int(time.time()), events=d["events"] + 1,
                 name=attrs.get("deviceName") or attrs.get("sourceDeviceName") or d.get("name"),
                 fields=sorted(set(d.get("fields") or []) | set(attrs)))
        paths.write_json_atomic(path, seen)
    except Exception:
        pass                                   # a record of who changed what never stops the channel


def notify_host(token=None):
    """Ask discovery where notifications live, as the official apps do."""
    st, b = _call("GET", "/discovery/v1/endpoints", token or user_token())
    if st != 200:
        return "eu.tectonic.remarkable.com"
    return json.loads(b).get("notifications") or "eu.tectonic.remarkable.com"


class Notifier(object):
    """Holds the push socket open in a thread and calls on_change(source_device) on SyncComplete.

    Never raises into the caller: when the socket cannot be held, `alive` goes False and the mirror keeper
    (keeper.py) checks on a timer until it is back, so losing it costs speed and nothing else.
    """

    def __init__(self, on_change=None):
        import threading
        self.on_change = on_change
        self.alive = False
        self.events = 0
        self.last_error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _connect(self):
        import socket
        import ssl
        if paths.local_only():
            raise LocalOnly("the false mirror never listens to the cloud")
        host = notify_host()
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1" + CRLF + "Host: %s" + CRLF +
               "Upgrade: websocket" + CRLF + "Connection: Upgrade" + CRLF +
               "Sec-WebSocket-Key: %s" + CRLF + "Sec-WebSocket-Version: 13" + CRLF +
               "Authorization: Bearer %s" + CRLF + CRLF)
        req = req % (NOTIFY_PATH, host, key, user_token())
        sock = ssl.create_default_context().wrap_socket(
            socket.create_connection((host, 443), timeout=20), server_hostname=host)
        sock.sendall(req.encode())
        head = sock.recv(4096)
        if b"101" not in head.split(CRLF.encode())[0]:
            sock.close()
            raise RuntimeError(head.split(CRLF.encode())[0].decode("utf-8", "replace"))
        return sock

    @staticmethod
    def _frame(buf):
        if len(buf) < 2:
            return None, buf
        op, ln, i = buf[0] & 0x0F, buf[1] & 0x7F, 2
        if ln == 126:
            ln, i = int.from_bytes(buf[2:4], "big"), 4
        elif ln == 127:
            ln, i = int.from_bytes(buf[2:10], "big"), 10
        if len(buf) < i + ln:
            return None, buf
        return (op, buf[i:i + ln]), buf[i + ln:]

    def _run(self):
        import socket
        backoff = 2
        while not self._stop.is_set():
            sock = None
            opened = time.time()
            try:
                sock = self._connect()
                opened = time.time()
                self.alive, self.last_error = True, None
                sock.settimeout(min(5.0, PING_AFTER / 2, PONG_WAIT / 2))      # how often the quiet is looked at
                buf = b""
                heard, pinged = time.time(), None
                while not self._stop.is_set():
                    try:
                        chunk = sock.recv(16384)
                    except socket.timeout:
                        # A LOST NETWORK IS SILENT: no error reaches a socket that is simply never answered. So after
                        # PING_AFTER seconds of quiet the connection pings, and a ping unanswered for PONG_WAIT means
                        # the network is gone (the server answers in well under a second).
                        now = time.time()
                        if pinged is not None and now - pinged > PONG_WAIT:
                            self.last_error = "no answer from the notice server: the network is gone"
                            break
                        if pinged is None and now - heard >= PING_AFTER:
                            m = os.urandom(4)
                            sock.sendall(bytes([0x89, 0x80 | 2]) + m + bytes(b ^ m[i % 4] for i, b in enumerate(b"pd")))
                            pinged = now
                        continue
                    heard, pinged = time.time(), None
                    if not chunk:
                        self.last_error = "server hung up with no data"
                        break
                    buf += chunk
                    while True:
                        f, buf = self._frame(buf)
                        if not f:
                            break
                        op, payload = f
                        if op == 8:                  # close
                            raise IOError("server closed")
                        if op == 10:                 # pong
                            continue
                        if op == 9:                  # ping -> pong
                            m = os.urandom(4)
                            sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + m +
                                         bytes(b ^ m[i % 4] for i, b in enumerate(payload)))
                            continue
                        if op != 1:
                            continue
                        try:
                            attrs = json.loads(payload.decode("utf-8", "replace")).get(
                                "message", {}).get("attributes", {})
                        except Exception:
                            attrs = {}
                        if attrs.get("sourceDeviceID"):
                            note_device(attrs)
                        if attrs.get("event") == "SyncComplete":
                            self.events += 1
                            if self.on_change:
                                self.on_change(attrs.get("sourceDeviceID"))
            except Exception as e:
                self.last_error = "%s: %s" % (type(e).__name__, str(e)[:80])
            finally:
                self.alive = False
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
            # Reset the backoff only for a connection that actually LIVED. The server accepts and
            # immediately closes while another client holds the channel; resetting on connect turns
            # that into a reconnect every two seconds against their servers.
            if time.time() - opened >= HEALTHY_AFTER:
                backoff = 2
            self._stop.wait(backoff + random.uniform(0, backoff * 0.25))
            backoff = min(backoff * 2, 300)


# ------------------------------------------------------------------- mirror
def _state():
    """What was last pulled: the root, its generation, each document's index hash and each file's hash.
    Entries for files gone from the mirror are dropped (once per mirror), so they are pulled again."""
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"root": None, "generation": 0, "docs": {}, "files": {}}
    if st.get("checked_against") != MIRROR:
        gone = [n for n in st.get("files", {}) if not os.path.exists(os.path.join(MIRROR, n.replace("/", os.sep)))]
        for n in gone:
            del st["files"][n]
        if gone:
            dead = {n.split("/")[0].split(".")[0] for n in gone}
            st["docs"] = {u: h for u, h in st.get("docs", {}).items() if u not in dead}
        st["checked_against"] = MIRROR
        _save_state(st)
    return st


def mirrored():
    """True once a pull has finished: the Mirror holds the whole library as of its last root. A false mirror is whole
    from the start: nothing ever arrives in it from elsewhere."""
    return paths.local_only() or bool(_state().get("root"))


def _save_state(st):
    os.makedirs(SAFETY, exist_ok=True)
    tmp = "%s.%d.tmp" % (STATE, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    replace(tmp, STATE)


def _write_atomic(relpath, data):
    """Temp file then rename, so a half-download never looks like a real page."""
    dest = os.path.join(MIRROR, relpath.replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    replace(tmp, dest)


# ONE PULL OR PUSH AT A TIME, across PaperDaemon's processes: the engine keeps the mirror current while the daemon
# pushes what jobs wrote, and both read and write the same record of what the cloud holds (mirror-state.json) and
# move the same root. Each holds this lock for its whole run, so neither writes over the other.
_LOCKS = {}


def _one_at_a_time(fn):
    import functools
    from paperdaemon.filelock import FileLock

    @functools.wraps(fn)
    def wrapped(*a, **k):
        path = os.path.join(SAFETY, "sync.lock")
        lock = _LOCKS.setdefault(path, FileLock(path))
        with lock:
            return fn(*a, **k)
    return wrapped


def _keep_our_pages(name, incoming, st):
    """A notebook's page list from the cloud, with the pages WE added and have not pushed yet put
    back. The tablet re-uploads a notebook's page list when it opens it, so a page added here and
    not yet pushed would vanish from the list, and every page number after it would move. When our
    copy holds unpushed changes, theirs is taken as it is -- their order, their deletions -- and only
    pages it has never heard of, whose .rm is here, are added back."""
    path = os.path.join(MIRROR, name.replace("/", os.sep))
    try:
        mine = open(path, "rb").read()
    except OSError:
        return incoming
    known = st["files"].get(name)
    if known is None or hashlib.sha256(mine).hexdigest() == known:
        return incoming                            # no local edit (or a stopped pull's download): nothing of ours
    try:
        theirs, ours = json.loads(incoming), json.loads(mine)
    except ValueError:
        return incoming
    tp = theirs.get("cPages", {}).get("pages")
    if not isinstance(tp, list):
        return incoming
    known = set(p.get("id") for p in tp)
    doc = name.split("/")[0].split(".")[0]
    extra = [p for p in ours.get("cPages", {}).get("pages", [])
             if p.get("id") not in known and "deleted" not in p
             and os.path.exists(os.path.join(MIRROR, doc, p["id"] + ".rm"))]
    if not extra:
        return incoming
    print("  kept %d page(s) of ours the cloud's %s does not know yet" % (len(extra), name))
    tp.extend(extra)
    theirs["pageCount"] = len([p for p in tp if "deleted" not in p])
    return json.dumps(theirs, indent=4).encode()


def _set_aside_unpushed(name, st):
    """The cloud has a new copy of a file whose local copy holds an edit not pushed yet: both changed. The tablet's
    copy is the user's and wins; ours is kept in <safety>/conflicts so nothing PaperDaemon wrote is silently lost."""
    path = os.path.join(MIRROR, name.replace("/", os.sep))
    try:
        mine = open(path, "rb").read()
    except OSError:
        return
    known = st["files"].get(name)
    if known is None or hashlib.sha256(mine).hexdigest() == known:
        # no local edit: a file no finished pull recorded is a download a stopped pull left behind, never an edit
        return
    keep = os.path.join(SAFETY, "conflicts", time.strftime("%Y%m%d-%H%M%S"), name.replace("/", os.sep))
    os.makedirs(os.path.dirname(keep), exist_ok=True)
    with open(keep, "wb") as f:
        f.write(mine)
    print("  the tablet changed %s too; our unpushed copy is kept in %s" % (name, keep))
    m = re.fullmatch(r"([0-9a-f-]{36})/([0-9a-f-]{36})\.rm", name)
    if m:
        record_conflict(m.group(1), m.group(2), keep)


def _conflicts_path():
    return os.path.join(SAFETY, "conflicts", "pending.json")


def pending_conflicts():
    """{"<doc>/<page id>": {"doc", "page_id", "ours", "at"}}: pages the tablet and a job both changed, waiting for
    their CONFLICT job. One per page."""
    try:
        with open(_conflicts_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def record_conflict(doc, page_id, ours):
    """A page both sides changed: its CONFLICT job is owed. A newer conflict on the same page replaces the older."""
    got = pending_conflicts()
    got["%s/%s" % (doc, page_id)] = {"doc": doc, "page_id": page_id, "ours": ours, "at": time.time()}
    paths.write_json_atomic(_conflicts_path(), got)


def take_conflict(key=None):
    """The oldest owed conflict (or the one named), removed from the list -> its record, or None."""
    got = pending_conflicts()
    if not got:
        return None
    k = key if key in got else min(got, key=lambda x: got[x].get("at") or 0)
    rec = got.pop(k)
    paths.write_json_atomic(_conflicts_path(), got)
    return rec


@_one_at_a_time
def pull(token=None, progress=None, plan=None):
    """Bring the mirror up to date with the cloud -> what changed.

    Cheap when nothing did: one request for the root hash, and if it matches the last one pulled,
    nothing else happens. Every download is checked against the hash the index advertised, so a
    corrupt blob is caught here, not later as a corrupt page. A document that leaves the account
    leaves the mirror: files the state no longer lists are removed.

    `plan(documents, size)`, when given, hears first how many documents changed and their size in bytes
    as the root index lists them; `progress(name, size)` then hears each file written, and
    `progress(None, 0)` each changed document finished.
    """
    t = token or user_token()
    root, gen = get_root(t)
    st = _state()
    catch_up = st.get("want") != WANT_KEY            # the mirror keeps more than when it was last pulled
    if root == st.get("root") and not catch_up:
        return {"changed": False, "root": root, "generation": gen}

    tree = get_blob(t, root, "root.docSchema").decode()
    docs, seen, got, dropped = {}, set(), [], []
    # smallest first: folders are a few hundred bytes, so the library's whole folder tree arrives at once, then the
    # notebooks, and the large PDFs and books last -- what is already there is usable while the rest comes
    def _size(line):
        f = line.split(":")
        return int(f[4]) if len(f) > 4 and f[4].isdigit() else 0
    lines = sorted(tree.splitlines()[1:], key=_size)
    if plan:
        changed = [l.split(":") for l in lines]
        changed = [f for f in changed if st["docs"].get(f[2]) != f[0]]
        plan(len(changed), sum(int(f[4]) for f in changed if f[4].isdigit()))
    # A PULL CAN STOP ANYWHERE (PaperDaemon quits, an update installs, the network drops) and a first pull of a big
    # library takes long. So what it has fetched is saved as it goes: each finished document goes into the state,
    # written every few seconds and when the pull stops for any reason, and the next pull carries on from there
    # instead of starting over and taking its own downloads for edits.
    last_save = time.time()
    try:
        for line in lines:
            dhash, _, uuid, _, _ = line.split(":")
            docs[uuid] = dhash
            if st["docs"].get(uuid) == dhash and not (catch_up and _is_template(uuid)):
                seen.update(k for k in st["files"] if k.split("/")[0].split(".")[0] == uuid)
                continue                       # this document is untouched
            _pull_document(t, dhash, uuid, st, seen, got, progress)
            st["docs"][uuid] = dhash           # this document is now as the cloud has it
            if time.time() - last_save >= 5:
                _save_state(st)
                last_save = time.time()
    finally:
        _save_state(st)                        # what was fetched stays fetched, whatever stopped the pull

    for name in [k for k in st["files"] if k not in seen]:
        p = os.path.join(MIRROR, name.replace("/", os.sep))
        if os.path.exists(p):
            os.remove(p)
        del st["files"][name]
        dropped.append(name)

    st.update(root=root, generation=gen, docs=docs, want=WANT_KEY)
    _save_state(st)
    return {"changed": True, "root": root, "generation": gen, "downloaded": got, "deleted": dropped}


def _pull_document(t, dhash, uuid, st, seen, got, progress):
    """One changed document's files into the mirror, each recorded in the state as it lands."""
    di = get_blob(t, dhash, uuid + ".docSchema").decode()
    for fl in di.splitlines()[1:]:
        fhash, _, name, _, _ = fl.split(":")
        if not name.endswith(WANT):
            continue
        seen.add(name)
        if st["files"].get(name) == fhash:
            continue                           # this file is untouched
        path = os.path.join(MIRROR, name.replace("/", os.sep))
        if os.path.isfile(path):
            with open(path, "rb") as f:
                here = f.read()
            if hashlib.sha256(here).hexdigest() == fhash:
                st["files"][name] = fhash      # already here, byte for byte (an earlier pull fetched it)
                if progress:
                    progress(name, len(here))  # it counts toward the bar like a download
                continue
        data = get_blob(t, fhash, name)
        if hashlib.sha256(data).hexdigest() != fhash:
            raise RuntimeError("corrupt download: %s" % name)
        if name.endswith(".content"):
            data = _keep_our_pages(name, data, st)
        else:
            _set_aside_unpushed(name, st)
        _write_atomic(name, data)
        st["files"][name] = fhash
        got.append(name)
        if progress:
            progress(name, len(data))
    if progress:
        progress(None, 0)


def changed_files(doc_uuid=None):
    """Files in the mirror whose bytes no longer match what was pulled: what "needs pushing" means.
    The state records every file's hash as the cloud had it, so any difference is a local edit."""
    st = _state()
    out = []
    for name, known in sorted(st["files"].items()):
        if doc_uuid and not name.startswith(doc_uuid):
            continue
        path = os.path.join(MIRROR, name.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if h != known:
            out.append((name, known, h))
    return out


def revert_since(doc_uuid, since, token=None):
    """Undo what was written to one document in the mirror since `since` (seconds) and never pushed: each of its
    files changed since then goes back to the bytes the cloud has, and each file of it the cloud never had (a page or
    a picture a job added) goes. Writes from before `since` -- an earlier job's push still owed -- are left alone.
    For a job the user abandons. -> [file names put back or removed]."""
    st = _state()
    out, t = [], None
    for name, known, _h in changed_files(doc_uuid):
        path = os.path.join(MIRROR, name.replace("/", os.sep))
        if os.path.getmtime(path) < since:
            continue
        t = t or token or user_token()
        data = get_blob(t, known, name)
        if hashlib.sha256(data).hexdigest() != known:
            raise RuntimeError("corrupt download: %s" % name)
        _write_atomic(name, data)
        out.append(name)
    top = os.path.join(MIRROR, doc_uuid)
    for dirpath, _dirs, files in os.walk(top):
        for fn in files:
            path = os.path.join(dirpath, fn)
            name = doc_uuid + "/" + os.path.relpath(path, top).replace(os.sep, "/")
            if name not in st["files"] and os.path.getmtime(path) >= since:
                os.remove(path)
                out.append(name)
    return out


def drop_new_since(since):
    """Remove every document the cloud never had that was made in the mirror since `since` (seconds): what an
    abandoned job created (a new notebook, a PDF document, a folder) goes with it. -> [document ids]."""
    st, out = _state(), []
    for f in os.listdir(MIRROR):
        if not f.endswith(".metadata"):
            continue
        u = f[:-len(".metadata")]
        path = os.path.join(MIRROR, f)
        if u in st.get("docs", {}) or os.path.getmtime(path) < since:
            continue
        for g in os.listdir(MIRROR):
            if g.split(".")[0] == u and os.path.isfile(os.path.join(MIRROR, g)):
                os.remove(os.path.join(MIRROR, g))
        if os.path.isdir(os.path.join(MIRROR, u)):
            import shutil
            shutil.rmtree(os.path.join(MIRROR, u))
        out.append(u)
    return out


# ------------------------------------------------------------------- the one way to the tablet
# EVERYTHING REACHES THE TABLET THROUGH push_pending. A job only writes to the mirror; the daemon pushes after the
# job is recorded, and the window's own sends (Decompose > send to the inbox) push the same way. Nothing else calls
# push_doc or push_new_doc: a job that pushed mid-way (an adventure's journal did) put on the tablet what an
# abandoned job could no longer take back.
def unpushed():
    """What the mirror holds that the cloud does not: (new documents, folders first and each folder before the
    folders inside it, [ids]; changed documents, {id: page ids touched})."""
    st = _state()
    known = st.get("docs", {})
    new, meta = [], {}
    for f in sorted(os.listdir(MIRROR)):
        if f.endswith(".metadata") and f[:-len(".metadata")] not in known:
            u = f[:-len(".metadata")]
            try:
                with open(os.path.join(MIRROR, f), encoding="utf-8") as fh:
                    meta[u] = json.load(fh)
            except (OSError, ValueError):
                continue
            new.append(u)

    def depth(u, n=0):
        p = (meta.get(u) or {}).get("parent")
        return depth(p, n + 1) if p in meta and n < 64 else n
    new.sort(key=lambda u: ((meta[u].get("type") != "CollectionType"), depth(u)))
    changed = {}
    for n, _, _ in changed_files():
        d = n.replace("\\", "/").split("/")[0].split(".")[0]
        if d in new:
            continue
        pages = changed.setdefault(d, set())
        if "/" in n and n.endswith(".rm"):
            pages.add(n.split("/", 1)[1][:-3])
    return new, changed


def push_pending(dry_run=False, log=None):
    """Push everything unpushed (unpushed()): new documents created, changed ones stamped -- so the tablet re-fetches
    the pages edited -- and updated. -> {"pushed": [(id, result)], "owed": True when the tablet changed some of
    them meanwhile (the next pull brings its change, and they go again)}.

    A BENCHMARK NEVER REACHES THE TABLET: its mirror is a copy of fixture notebooks the cloud never had, all of them
    "new" -- RM_HOST_DRY_DOCS=1 (the benchmark's environment) means nothing goes up at all, not even a dry look."""
    if os.environ.get("RM_HOST_DRY_DOCS") == "1" or paths.local_only():      # the false mirror: never the cloud
        return {"pushed": [], "owed": False}
    new, changed = unpushed()
    out, owed = [], False
    for u in new:
        r = push_new_doc(u, dry_run=dry_run)
        if isinstance(r, dict) and "already exists" in str(r.get("error", "")):
            r = push_doc(u, dry_run=dry_run)
        out.append((u, r))
    for d, pages in sorted(changed.items()):
        if not dry_run:
            try:
                t_ = touch(d, sorted(pages) or None)
                if log and t_.get("files"):
                    log("  stamped %s: %s" % (d[:8], ", ".join(t_["files"])[:60]))
            except Exception as ex:
                if log:
                    log("  stamp failed for %s: %s" % (d[:8], str(ex)[:70]))
        r = push_doc(d, dry_run=dry_run)
        out.append((d, r))
        if isinstance(r, dict) and r.get("theirs"):
            owed = True
    return {"pushed": out, "owed": owed}


# PaperDaemon never permanently deletes. Trashing (parent = "trash", pushed) is the ceiling of its
# authority; when a document actually leaves the account is the cloud's rule. So nothing here ever
# drops a line from root.docSchema.


# ------------------------------------------------------------------- push
def _is_folder(doc_uuid):
    try:
        with open(os.path.join(MIRROR, doc_uuid + ".metadata"), encoding="utf-8") as f:
            return json.load(f).get("type") == "CollectionType"
    except (OSError, ValueError):
        return False


def _local_files(doc_uuid):
    """{index name: path} for every file of one document in the mirror: its .content/.metadata/
    .pagedata, its source PDF/EPUB (a replaced source must go up with the page list describing it),
    each live page's .rm, and each page's pictures (one folder down, beside the page). A folder is its
    metadata (and .content when it has one) alone."""
    local = {}
    for suffix in (".content", ".metadata", ".pagedata", ".pdf", ".epub", ".epubindex", ".template"):
        f = os.path.join(MIRROR, doc_uuid + suffix)
        if os.path.exists(f):
            local[doc_uuid + suffix] = f
    for pg in [] if _is_folder(doc_uuid) else live_pages(content(doc_uuid)):
        pid = pg.get("id")
        if not pid:
            continue
        f = os.path.join(MIRROR, doc_uuid, pid + ".rm")
        if os.path.exists(f):
            local["%s/%s.rm" % (doc_uuid, pid)] = f
        pdir = os.path.join(MIRROR, doc_uuid, pid)
        if os.path.isdir(pdir):
            for fn in sorted(os.listdir(pdir)):
                if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                    local["%s/%s/%s" % (doc_uuid, pid, fn)] = os.path.join(pdir, fn)
    return local


def _upload(t, blobs):
    for data, fn, addr in blobs:
        st_, body, _ = put_blob(t, data, fn, addr)
        if st_ not in (200, 201, 202):
            raise RuntimeError("upload %s failed: %s %s" % (fn, st_, body[:120]))


@_one_at_a_time
def push_doc(doc_uuid, dry_run=True, replace=None, only=False):
    """Push every locally changed file of one existing document in a single root move.

    Diffs against the LIVE document index, not the cached state (the tablet may have pushed since),
    and includes files the index does not list at all -- a new page's .rm has no index line, and
    missing it would push a page list naming a page the cloud never received.

    `replace` = {index name ("<doc>/<page>.rm"): bytes} pushes those bytes for that file instead of the mirror's: a
    COPY of a page goes up while the page in the mirror stays as it is (the daemon's notes, pipeline/daemon/notes.py,
    while the host works on the page). The copy is recorded as the cloud's, so the next pull leaves the mirror's
    page alone, and the next push of the mirror's page takes the copy's place. `only`: those files and nothing else
    of the document -- a note going up mid-job never carries the job's own work with it (push_pending is the one way
    a job's work reaches the tablet, so it can still be taken back).
    """
    replace = replace or {}

    def _read(name, path):
        return replace[name] if name in replace else open(path, "rb").read()
    t = user_token()
    root, gen = get_root(t)
    tree = get_blob(t, root, "root.docSchema").decode()
    troot, tdocs = tree.splitlines()[0], tree.splitlines()[1:]
    lines = [l for l in tdocs if l.split(":")[2] == doc_uuid]
    if not lines:
        return {"error": "no such document in the cloud; use push_new_doc"}
    dline = lines[0]
    dhash, dflags, _, dcount, dsize = dline.split(":")
    di = get_blob(t, dhash, doc_uuid + ".docSchema").decode()
    dhead, dfiles = di.splitlines()[0], di.splitlines()[1:]

    local = _local_files(doc_uuid)
    if only:
        local = {n: p for n, p in local.items() if n in replace}
    indexed = {l.split(":")[2]: l for l in dfiles}
    pulled = _state()["files"]
    edits, added, theirs = [], [], []
    for name, path in sorted(local.items()):
        h = hashlib.sha256(_read(name, path)).hexdigest()
        line = indexed.get(name)
        if line is None:
            added.append((name, h, len(_read(name, path))))
            continue
        cloud = line.split(":")[0]
        if cloud == h:
            continue
        # ONLY WHAT PAPERDAEMON CHANGED goes up: a file whose local copy is still the one last pulled was changed
        # on the TABLET since, and uploading our older copy would undo the user's writing. And a file both sides
        # changed is the tablet's: the next pull brings it down (our copy is kept aside then).
        base = pulled.get(name)
        if base == h or (base is not None and base != cloud):
            theirs.append(name)
            continue
        edits.append((name, cloud, h))
    if not edits and not added:
        out = {"skipped": "the cloud already matches the mirror"}
        if theirs:
            out = {"skipped": "the tablet changed this document since the last pull; pull first",
                   "theirs": [n.split("/")[-1] for n in theirs]}
        return out

    blobs, nfiles, delta = [], list(dfiles), 0
    for name, known, newhash in edits:
        data = _read(name, local[name])
        i = [k for k, l in enumerate(nfiles) if l.split(":")[2] == name][0]
        ohash, oflags, _, ozero, osize = nfiles[i].split(":")
        delta += len(data) - int(osize)
        nfiles[i] = "%s:%s:%s:%s:%d" % (newhash, oflags, name, ozero, len(data))
        blobs.append((data, name, None))
    for name, newhash, size in added:
        data = _read(name, local[name])
        # the index is SORTED by file name, and the document hash is taken over it in that order
        nfiles.append("%s:0:%s:0:%d" % (newhash, name, size))
        nfiles.sort(key=lambda l: l.split(":")[2])
        delta += size
        blobs.append((data, name, None))
    assert len(nfiles) == len(dfiles) + len(added), "the index grew by the wrong amount"

    ndi = "\n".join([dhead] + nfiles) + "\n"
    ndhash = index_hash([l.split(":")[0] for l in nfiles])
    ndline = "%s:%s:%s:%s:%d" % (ndhash, dflags, doc_uuid, dcount, int(dsize) + delta)
    ndocs = [ndline if l is dline else l for l in tdocs]
    assert sum(a != b for a, b in zip(tdocs, ndocs)) == 1, "root: the wrong number of lines changed"
    ntree = "\n".join([troot] + ndocs) + "\n"
    nrhash = index_hash([l.split(":")[0] for l in ndocs])

    plan = {"doc": doc_uuid[:8], "files": [n.split("/")[-1] for n, _, _ in edits],
            "new_files": [n.split("/")[-1] for n, _, _ in added],
            "root": "%s -> %s" % (root[:12], nrhash[:12]), "generation": gen}
    if theirs:
        plan["theirs"] = [n.split("/")[-1] for n in theirs]       # left to the next pull
    if dry_run:
        plan["dry_run"] = True
        return plan

    blobs.append((ndi.encode(), doc_uuid + ".docSchema", ndhash))
    blobs.append((ntree.encode(), "root.docSchema", nrhash))
    _upload(t, blobs)
    code, body = put_root(t, nrhash, gen, broadcast=True)
    plan["root_put"] = code
    if code == 200:
        stt = _state()
        for name, _, newhash in edits:
            stt["files"][name] = newhash
        for name, newhash, _ in added:
            stt["files"][name] = newhash
        if not theirs:
            stt.update(root=nrhash, generation=json.loads(body)["generation"],
                       docs=dict(stt["docs"], **{doc_uuid: ndhash}))
        # else the document is NOT marked pulled: the tablet's pages in it are still to come down
        _save_state(stt)
    return plan


@_one_at_a_time
def push_new_doc(doc_uuid, dry_run=True):
    """Upload a document the cloud has never seen: every file of it, its index, and a root index
    with ONE added line, in a single root move. A PDF or EPUB document without its source file would
    open blank on the tablet, so the source goes up with it."""
    t = user_token()
    root, gen = get_root(t)
    tree = get_blob(t, root, "root.docSchema").decode()
    troot, tdocs = tree.splitlines()[0], tree.splitlines()[1:]
    if any(l.split(":")[2] == doc_uuid for l in tdocs):
        return {"error": "the document already exists in the cloud; use push_doc"}

    local = _local_files(doc_uuid)
    if doc_uuid + ".metadata" not in local or (doc_uuid + ".content" not in local and not _is_folder(doc_uuid)):
        return {"error": "the mirror has no .content/.metadata for that document"}

    files, blobs, total = [], [], 0
    for name, path in sorted(local.items()):            # the index is sorted by file name
        data = open(path, "rb").read()
        h = hashlib.sha256(data).hexdigest()
        files.append("%s:0:%s:0:%d" % (h, name, len(data)))
        blobs.append((data, name, None))
        total += len(data)
    ndi = "\n".join(["3"] + files) + "\n"
    ndhash = index_hash([l.split(":")[0] for l in files])
    dline = "%s:80000000:%s:%d:%d" % (ndhash, doc_uuid, len(files), total)
    ndocs = tdocs + [dline]
    if tdocs == sorted(tdocs, key=lambda l: l.split(":")[2]):
        ndocs.sort(key=lambda l: l.split(":")[2])        # keep the root's order convention
    assert len(ndocs) == len(tdocs) + 1
    ntree = "\n".join([troot] + ndocs) + "\n"
    nrhash = index_hash([l.split(":")[0] for l in ndocs])

    plan = {"doc": doc_uuid[:8], "files": len(files), "bytes": total,
            "root": "%s -> %s" % (root[:12], nrhash[:12]), "generation": gen}
    if dry_run:
        plan["dry_run"] = True
        return plan

    blobs.append((ndi.encode(), doc_uuid + ".docSchema", ndhash))
    blobs.append((ntree.encode(), "root.docSchema", nrhash))
    _upload(t, blobs)
    code, body = put_root(t, nrhash, gen, broadcast=True)
    plan["root_put"] = code
    if code == 200:
        stt = _state()
        for name, path in local.items():
            stt["files"][name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        stt.update(root=nrhash, generation=json.loads(body)["generation"],
                   docs=dict(stt["docs"], **{doc_uuid: ndhash}))
        _save_state(stt)
    return plan


@_one_at_a_time
def delete_doc(doc_uuid):
    """Remove a document from the cloud OUTRIGHT -- its line taken out of the root index, in one root move; not moved to
    the trash -- and its files from the mirror. Only for a document PaperDaemon itself put there (a book sent to the
    tablet to be converted for the false mirror). -> {"deleted": bool} or {"error": ...}."""
    t = user_token()
    root, gen = get_root(t)
    tree = get_blob(t, root, "root.docSchema").decode()
    troot, tdocs = tree.splitlines()[0], tree.splitlines()[1:]
    ndocs = [l for l in tdocs if l.split(":")[2] != doc_uuid]
    if len(ndocs) == len(tdocs):
        out = {"deleted": False, "why": "not in the cloud"}
    else:
        ntree = "\n".join([troot] + ndocs) + "\n"
        nrhash = index_hash([l.split(":")[0] for l in ndocs])
        _upload(t, [(ntree.encode(), "root.docSchema", nrhash)])
        code, body = put_root(t, nrhash, gen, broadcast=True)
        if code != 200:
            return {"error": "the cloud refused the root move (%s)" % code}
        stt = _state()
        stt.update(root=nrhash, generation=json.loads(body)["generation"],
                   docs={k: v for k, v in stt["docs"].items() if k != doc_uuid},
                   files={k: v for k, v in stt["files"].items() if not k.startswith(doc_uuid)})
        _save_state(stt)
        out = {"deleted": True}
    import shutil
    for f in os.listdir(MIRROR):
        if f.startswith(doc_uuid + "."):
            p = os.path.join(MIRROR, f)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    shutil.rmtree(os.path.join(MIRROR, doc_uuid), ignore_errors=True)
    return out


def touch(doc_uuid, page_ids=None, when=None):
    """Say the document CHANGED, so the tablet re-fetches the pages that were edited.

    Pushing a new .rm updates the content but leaves <doc>.metadata's lastModified and the page's
    `modifed` in <doc>.content at what the TABLET last set. The tablet then sees timestamps equal to
    its own copy and never re-renders the page. Call this BEFORE push_doc, with the pages touched, so
    .metadata and .content go up in the same root move as the pages.
    """
    ms = int((when or time.time()) * 1000)
    changed = []
    mp = os.path.join(MIRROR, doc_uuid + ".metadata")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8"))
        m["lastModified"] = str(ms)
        m.pop("new", None)          # a device-written "new" can read as freshly created, not updated
        tmp = mp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=4)
        replace(tmp, mp)
        changed.append(os.path.basename(mp))
    cp = os.path.join(MIRROR, doc_uuid + ".content")
    if os.path.exists(cp):
        c = json.load(open(cp, encoding="utf-8"))
        pages = c.get("cPages", {}).get("pages", [])
        want = set(page_ids or [p.get("id") for p in pages])
        hit = 0
        for p in pages:
            if p.get("id") in want and "deleted" not in p:
                p["modifed"] = str(ms)          # sic: the field is spelled this way in the format
                hit += 1
        if hit:
            tmp = cp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(c, f, indent=4)
            replace(tmp, cp)
            changed.append(os.path.basename(cp))
    return {"doc": doc_uuid[:8], "stamped": ms, "files": changed}


if __name__ == "__main__":
    if sys.argv[1:2] == ["pull"]:
        r = pull(progress=lambda n, b: n and print("  %s (%d bytes)" % (n, b)))
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}, indent=1))
    else:
        h, g = get_root()
        print("root hash : %s\ngeneration: %s\nmirror    : %s" % (h, g, MIRROR))
