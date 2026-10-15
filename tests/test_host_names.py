"""Every name the host's modules use is defined: a module's own globals and imports, the builtins, and every
H.<name> it reads from the host. The modules reach each other through H at call time, so a name that went away
would only show when a job reached it."""
import ast
import builtins
import os
import symtable

import paperdaemon.pipeline.host as H

HOST = os.path.dirname(H.__file__)


def _modules():
    for d, _, fs in os.walk(HOST):
        if "__pycache__" in d:
            continue
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(d, f)


def _defined(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.Global):
            out.update(n.names)
    return out


def _globals_used(table, out):
    for s in table.get_symbols():
        if s.is_global() and s.is_referenced():
            out.add(s.get_name())
    for c in table.get_children():
        _globals_used(c, out)


def test_every_global_a_host_module_reads_is_defined():
    missing = []
    for path in _modules():
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        have = _defined(tree) | set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
        used = set()
        _globals_used(symtable.symtable(src, path, "exec"), used)
        missing += ["%s: %s" % (os.path.relpath(path, HOST), n) for n in sorted(used - have)]
    assert missing == []


def test_every_name_read_through_H_exists():
    """In a module that imports the host as H, every H.<name> it reads exists -- and no function there takes H
    for anything else (a parameter or a local named H would turn the host's names into its own)."""
    missing = []
    for path in _modules():
        tree = ast.parse(open(path, encoding="utf-8").read())
        if not any(isinstance(n, ast.ImportFrom) and any(a.asname == "H" for a in n.names) for n in tree.body):
            continue
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            local = [a.arg for a in fn.args.args + fn.args.kwonlyargs] + \
                    [n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]
            if "H" in local:
                missing.append("%s: %s() has its own H" % (os.path.relpath(path, HOST), fn.name))
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "H" \
                    and isinstance(n.ctx, ast.Load) and not hasattr(H, n.attr):
                missing.append("%s:%d: H.%s" % (os.path.relpath(path, HOST), n.lineno, n.attr))
    assert missing == []
