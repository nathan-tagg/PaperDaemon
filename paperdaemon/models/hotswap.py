"""Running a slot's start script and waiting for its server, by the start-script contract
(paperdaemon/scripts.py).

PaperDaemon ends only what it started. On Windows each script runs inside a job object of its own,
created with kill-on-close: ending the server ends that job and every process in it, and if PaperDaemon
itself dies, Windows closes the job's handle and ends the server with it. The script is created
suspended and resumed only once it is inside its job, so nothing it spawns can slip out. Elsewhere a
script runs in its own process group.

A script's output is kept in memory, the last lines only, to explain a failed start. It is never
written to disk.

A server answering on the slot's location is PaperDaemon's only when the process listening on that port
is inside the script's job (checked on Windows for a location on this computer). A server some other
program left on the port is never taken for PaperDaemon's own.

Waiting has no clock: it lasts while the script or anything it started is alive, and ends when the
location answers, when everything the script started has exited, or when the caller cancels.
"""
import atexit
import collections
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

from .. import paths, scripts
from .. import settings as S
from . import adapters, slots

WINDOWS = sys.platform == "win32"
POLL = 0.5
OUTPUT_LINES = 200


class LaunchFailed(Exception):
    pass


# ---------------------------------------------------------------- Windows job objects

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")
    _JOB_KILL_ON_CLOSE = 0x2000
    _JOB_EXTENDED_LIMITS = 9
    _CREATE_SUSPENDED = 0x00000004

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r_ops", "w_ops", "o_ops", "r_bytes", "w_bytes", "o_bytes")]

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _EXTENDED(ctypes.Structure):
        _fields_ = [("Basic", _BASIC), ("Io", _IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.CloseHandle.restype = wintypes.BOOL
    _ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
    _ntdll.NtResumeProcess.restype = ctypes.c_long

    class _ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    _k32.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD))
    _k32.QueryInformationJobObject.restype = wintypes.BOOL

    def _job_active(job):
        """True while any process in the job is running (a script may hand off to a server and exit)."""
        info = _ACCOUNTING()
        ok = _k32.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None)
        return bool(ok) and info.ActiveProcesses > 0

    def _new_job():
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        info = _EXTENDED()
        info.Basic.LimitFlags = _JOB_KILL_ON_CLOSE
        if not _k32.SetInformationJobObject(job, _JOB_EXTENDED_LIMITS, ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.get_last_error()
            _k32.CloseHandle(job)
            raise OSError(err, "SetInformationJobObject failed")
        return job



    # ---- who listens on a port: the TCP tables with owning process ids
    _iphlp = ctypes.WinDLL("iphlpapi")
    _iphlp.GetExtendedTcpTable.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                                           wintypes.ULONG, ctypes.c_int, wintypes.ULONG)
    _iphlp.GetExtendedTcpTable.restype = wintypes.DWORD
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    _k32.IsProcessInJob.restype = wintypes.BOOL
    _TCP_TABLE_OWNER_PID_LISTENER = 3
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def _listeners(port):
        """The ids of the processes listening on a TCP port, IPv4 and IPv6. None when the table cannot
        be read."""
        pids = set()
        for family, row_size, port_at, pid_at in ((socket.AF_INET, 24, 8, 20), (socket.AF_INET6, 56, 20, 52)):
            size = wintypes.DWORD(0)
            _iphlp.GetExtendedTcpTable(None, ctypes.byref(size), False, family, _TCP_TABLE_OWNER_PID_LISTENER, 0)
            buf = ctypes.create_string_buffer(size.value + 4096)
            size = wintypes.DWORD(len(buf))
            if _iphlp.GetExtendedTcpTable(buf, ctypes.byref(size), False, family,
                                          _TCP_TABLE_OWNER_PID_LISTENER, 0) != 0:
                return None
            raw = buf.raw
            n = int.from_bytes(raw[0:4], "little")
            for i in range(n):
                row = raw[4 + i * row_size: 4 + (i + 1) * row_size]
                p = int.from_bytes(row[port_at:port_at + 4], "little") & 0xFFFF
                if socket.ntohs(p) == port:
                    pids.add(int.from_bytes(row[pid_at:pid_at + 4], "little"))
        return pids

    def _in_job(job, pid):
        h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            got = wintypes.BOOL(False)
            if not _k32.IsProcessInJob(h, job, ctypes.byref(got)):
                return None
            return bool(got.value)
        finally:
            _k32.CloseHandle(h)


# ---------------------------------------------------------------- the servers PaperDaemon started

class Server:
    def __init__(self, role, proc, job, script, lineup, key=""):
        self.role, self.proc, self.job, self.script, self.lineup = role, proc, job, script, lineup
        self.key = key                               # scripts.identity of the slot it was started for
        self.started = time.time()
        self.output = collections.deque(maxlen=OUTPUT_LINES)
        self.ready = False
        threading.Thread(target=self._read, name="server-%s-output" % role, daemon=True).start()

    def _read(self):
        for line in iter(self.proc.stdout.readline, b""):
            self.output.append(line.decode("utf-8", "replace").rstrip())

    def alive(self):
        """The script, or anything it started, is still running."""
        if self.proc.poll() is None:
            return True
        if WINDOWS:
            return bool(self.job) and _job_active(self.job)
        try:
            os.killpg(self.proc.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def owns_listener(self, location):
        """True when the process listening on the location's port is one this script started; None when
        that cannot be told (not Windows, a location on another computer, or the table unreadable)."""
        if not WINDOWS or not self.job or not S.loopback(location):
            return None
        try:
            port = urllib.parse.urlsplit(location).port or (443 if location.startswith("https") else 80)
        except ValueError:
            return None
        pids = _listeners(port)
        if not pids:
            return None if pids is None else False
        seen = [_in_job(self.job, pid) for pid in pids]
        if any(v is True for v in seen):
            return True
        return None if all(v is None for v in seen) else False

    def tail(self, n=12):
        return list(self.output)[-n:]


_servers = {}                  # role -> Server
_lock = threading.RLock()


def environment(role, s=None, lineup=None):
    """The variables a start script is given (the contract in paperdaemon/scripts.py)."""
    s = s or S.load()
    lu = S.lineup(s, lineup) if lineup else S.active(s)
    other = "image" if role == "text" else "text"
    loc = str(lu[role].get("location") or "").strip()
    host, port = "", ""
    if loc:
        try:
            parts = urllib.parse.urlsplit(loc)
            host = parts.hostname or ""
            port = str(parts.port or (443 if parts.scheme == "https" else 80))
        except ValueError:
            pass
    env = dict(os.environ)
    env.update(PAPERDAEMON_ROLE=role, PAPERDAEMON_LOCATION=loc, PAPERDAEMON_HOST=host, PAPERDAEMON_PORT=port,
               PAPERDAEMON_OTHER_LOCATION=str(lu[other].get("location") or "").strip(),
               PAPERDAEMON_LINEUP=str(lu.get("name") or ""), PAPERDAEMON_DATA=paths.data_dir())
    return env


def _command(path):
    low = path.lower()
    if low.endswith((".bat", ".cmd")):
        return ["cmd.exe", "/d", "/c", path]
    if low.endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
    return ["/bin/sh", path]


def _spawn(path, env):
    cwd = os.path.dirname(path)
    if WINDOWS:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                           # SW_HIDE: a console of its own, never on screen
        job = _new_job()
        try:
            proc = subprocess.Popen(_command(path), cwd=cwd, env=env, startupinfo=si,
                                    creationflags=subprocess.CREATE_NEW_CONSOLE | _CREATE_SUSPENDED,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError:
            _k32.CloseHandle(job)
            raise
        handle = int(proc._handle)
        if not _k32.AssignProcessToJobObject(job, handle):
            err = ctypes.get_last_error()
            proc.kill()
            _k32.CloseHandle(job)
            raise OSError(err, "could not place the server in its job object")
        _ntdll.NtResumeProcess(handle)
        return proc, job
    proc = subprocess.Popen(_command(path), cwd=cwd, env=env, start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc, None


def _close_job(server):
    if WINDOWS and server.job:
        job, server.job = server.job, None
        _k32.CloseHandle(job)


def _end(server):
    if WINDOWS:
        job, server.job = server.job, None           # never touch a closed handle again
        if not job:
            return
        _k32.TerminateJobObject(job, 1)
        try:
            server.proc.wait(timeout=30)
        finally:
            _k32.CloseHandle(job)
        return
    try:
        os.killpg(server.proc.pid, signal.SIGTERM)
        server.proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(server.proc.pid, signal.SIGKILL)
        server.proc.wait()
    except ProcessLookupError:
        pass


# ---------------------------------------------------------------- the public surface

def answering(role, s=None, m=None):
    """True when the slot's location answers and is ready (whoever's server it is). `m`: another lineup's slot."""
    m = m if m is not None else slots.slot(role, s)
    if not str(m.get("location") or "").strip():
        return False
    return adapters.for_slot(role, s, m).health()


def needed(role, s=None):
    """The start script the lineup in use needs for `role` (scripts.identity), "" when it needs none."""
    return scripts.identity(slots.slot(role, s))


def ours(role):
    """The running server PaperDaemon started for `role` (its job object is not empty), or None."""
    with _lock:
        srv = _servers.get(role)
        return srv if srv is not None and srv.alive() else None


def last(role):
    """The latest server record for `role`, running or not (for its output after a failure)."""
    return _servers.get(role)


def status(role, s=None, m=None):
    srv = ours(role)
    up = answering(role, s, m)
    return {"answering": up, "started_by_paperdaemon": srv is not None,
            "loading": bool(srv is not None and not srv.ready),
            "since": srv.started if srv else None,
            "pid": srv.proc.pid if srv else None,
            "lineup": srv.lineup if srv else None}


def start(role, s=None, cancel=None, on_wait=None):
    """Run the slot's start script and wait until the location answers, by the contract. -> Server.

    `cancel` (a threading.Event) stops the wait early and ends what the script started; `on_wait(seconds)`
    is called while waiting so a caller can show progress."""
    s = s or S.load()
    m = slots.slot(role, s)
    loc = slots.location(role, s)
    if not loc:
        raise LaunchFailed("the %s slot has no location" % role)
    if not scripts.has_script(m):
        raise LaunchFailed("the %s slot has no start script" % role)
    lineup = S.active(s)["name"]
    key = scripts.identity(m)
    with _lock:
        srv = ours(role)
        if srv is not None and srv.key != key:
            # ANOTHER LINEUP'S SERVER holds this role: the last start script loaded is not the one this job
            # needs, so it ends first (the card is the user's; two local servers rarely fit on it)
            stop(role)
            srv = None
        if srv is None:
            try:
                path = scripts.runnable(role, m)
            except OSError as ex:
                raise LaunchFailed(str(ex))
            old = _servers.get(role)
            if old is not None:
                _close_job(old)
            proc, job = _spawn(path, environment(role, s))
            srv = _servers[role] = Server(role, proc, job, path, lineup, key)
    while True:
        if srv.alive():
            if answering(role, s) and srv.owns_listener(loc) is not False:
                srv.ready = True
                return srv
        else:
            code = srv.proc.poll()
            if code == 0 and answering(role, s):
                # the script handed its server to something outside PaperDaemon and exited cleanly
                _close_job(srv)
                srv.ready = True
                return srv
            _close_job(srv)
            tail = " | ".join(srv.tail(6))
            raise LaunchFailed("the %s start script ended (exit code %s) and %s is not answering%s"
                               % (role, code, loc, ": " + tail if tail else ""))
        if cancel is not None and cancel.is_set():
            stop(role)
            raise LaunchFailed("starting the %s server was canceled" % role)
        if on_wait:
            on_wait(time.time() - srv.started)
        time.sleep(POLL)


def stop(role):
    """End what the slot's start script started, if it is still running. -> True if anything was."""
    with _lock:
        srv = _servers.pop(role, None)
    if srv is None:
        return False
    was = srv.alive()
    _end(srv)
    return was


def stop_all():
    for role in list(_servers):
        try:
            stop(role)
        except Exception:
            pass


atexit.register(stop_all)
