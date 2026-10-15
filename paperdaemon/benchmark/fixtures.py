"""Builds the benchmark's fixture pages with the pipeline's own writers, deterministically: the same ids,
times and content every time, so every run (and every lineup) works on identical pages.

    uv run python -m paperdaemon.benchmark.fixtures [--out tests/benchmark/cases]

Each case becomes a folder holding case.json (what is asked and what counts as a pass) and mirror/, a
one-notebook library in the tablet's own file format: the notebook's .metadata and .content, and its
one page's .rm, with the trigger tag on the page. Run as its own process: the pipeline's modules read the
mirror's location from the environment when they are imported.
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(HERE)
PIPELINE = os.path.join(PACKAGE, "pipeline")
DEFAULT_OUT = os.path.join(os.path.dirname(PACKAGE), "tests", "benchmark", "cases")

TAG = "PaperDaemon"                  # the trigger tag on every fixture page; the runner uses the same
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://paperdaemon.invalid/benchmark")
WHEN = 1767225600000                 # one fixed time, in milliseconds, for every fixture timestamp

# id, title, how the request is written (typed: keyboard text; ink: pen strokes in a handwriting-style
# font), the request, and what a passing answer puts on the page
CASES = [
    {"id": "typed-question", "title": "A typed question", "kind": "typed",
     "request": "How many moons does Mars have, and what are they called?",
     "expect": {"content": "text"}},
    {"id": "ink-question", "title": "A handwritten question", "kind": "ink",
     "request": "How many legs does a spider have?",
     "expect": {"content": "text"}},
    {"id": "draw", "title": "Draw a picture", "kind": "typed",
     "request": "Draw a lighthouse on a rocky shore.",
     "expect": {"content": "drawing"}},
    {"id": "chart", "title": "A chart", "kind": "typed",
     "request": "Make a bar chart of the diameters of the four inner planets.",
     "expect": {"content": "chart"}},
    {"id": "coloring-page", "title": "A coloring page", "kind": "typed",
     "request": "Make a coloring page of a friendly dragon.",
     "expect": {"content": "picture"}},
]


def ids(case_id):
    """The notebook's and the page's fixed ids for a case."""
    return (str(uuid.uuid5(NAMESPACE, "doc:" + case_id)), str(uuid.uuid5(NAMESPACE, "page:" + case_id)))


def _blank_page():
    from rmscene import read_blocks, write_blocks
    from rmscene import scene_stream as ss
    with open(os.path.join(PIPELINE, "rm-templates", "blank-page.rm"), "rb") as f:
        data = f.read()
    blocks = [b for b in read_blocks(io.BytesIO(data))
              if not isinstance(b, (ss.SceneLineItemBlock, ss.RootTextBlock))]
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    return buf.getvalue()


def _notebook(mirror, case):
    doc, pid = ids(case["id"])
    with open(os.path.join(PIPELINE, "rm-templates", "notebook.content"), encoding="utf-8") as f:
        tpl = json.load(f)
    content = dict(tpl)
    page = {"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}, "modifed": str(WHEN),
            "template": {"timestamp": "1:1", "value": "Blank"}}
    content["cPages"] = {"lastOpened": {"timestamp": "1:1", "value": pid},
                         "original": {"timestamp": "0:0", "value": -1},
                         "pages": [page], "uuids": tpl["cPages"]["uuids"]}
    blank = _blank_page()
    content.update(pageCount=1, coverPageNumber=0, sizeInBytes=str(len(blank)), tags=[],
                   pageTags=[{"name": TAG, "pageId": pid, "timestamp": WHEN + 1000}])
    os.makedirs(os.path.join(mirror, doc), exist_ok=True)
    with open(os.path.join(mirror, doc, pid + ".rm"), "wb") as f:
        f.write(blank)
    with open(os.path.join(mirror, doc + ".content"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=4)
    with open(os.path.join(mirror, doc + ".metadata"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"createdTime": str(WHEN), "lastModified": str(WHEN), "lastOpened": "", "lastOpenedPage": 0,
                   "parent": "", "pinned": False, "source": "", "type": "DocumentType",
                   "visibleName": "Benchmark - " + case["title"]}, f, indent=4)
    with open(os.path.join(mirror, doc + ".pagedata"), "w", encoding="utf-8", newline="\n") as f:
        f.write("Blank\n")
    return doc, pid


def _write_request(doc, case):
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline.draw import lettering as T
    from paperdaemon.pipeline.page import typed as TY
    if case["kind"] == "typed":
        TY.insert(doc, 1, case["request"])
    else:
        d = A.Drawing()
        T.paragraph(d, case["request"], -600, 360, 1200, size=44, width=13, seed=7)
        d.write_rm(doc, 1, keep_existing=True)


def build(out):
    """Write every case under `out` (replacing what was there). -> the case ids."""
    work = tempfile.mkdtemp(prefix="paperdaemon-fixtures-")
    try:
        mirror = os.path.join(work, "mirror")
        os.makedirs(mirror)
        os.environ.update(RM_CACHE=mirror, RM_MIRROR=mirror, RM_STATE=os.path.join(work, "state"))
        os.makedirs(os.environ["RM_STATE"], exist_ok=True)
        if PIPELINE not in sys.path:
            sys.path.insert(0, PIPELINE)
        os.makedirs(out, exist_ok=True)
        done = []
        for case in CASES:
            doc, pid = _notebook(mirror, case)
            _write_request(doc, case)
            dest = os.path.join(out, case["id"])
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            os.makedirs(os.path.join(dest, "mirror", doc))
            for n in (doc + ".metadata", doc + ".content", doc + ".pagedata"):
                shutil.copyfile(os.path.join(mirror, n), os.path.join(dest, "mirror", n))
            shutil.copyfile(os.path.join(mirror, doc, pid + ".rm"), os.path.join(dest, "mirror", doc, pid + ".rm"))
            meta = dict(case, doc=doc, page=pid, tag=TAG)
            with open(os.path.join(dest, "case.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, indent=2)
            done.append(case["id"])
        return done
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the benchmark's fixture pages.")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    for c in build(os.path.abspath(args.out)):
        print(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
