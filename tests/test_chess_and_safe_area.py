"""The chess page and the safe area: a first move in the request is played before the opponent replies, the
board is as wide as the safe area allows with its coordinates inside it, and every kind of content starts
below the tablet's toolbar. The pipeline reads where its files are when it is imported, so its modules run
in a process of their own."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(tmp_path, body):
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import paperdaemon.pipeline  # noqa: F401
    """) % ROOT + textwrap.dedent(body)
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"),
               PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_requests_first_move_is_played_and_checked(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        out = {}
        st = CH.new_game("doc", "pid", user_color="w")
        out["e4"] = CH.play_opening(st, ["e4"]) + (st["fen"], st["history"][0]["by"])
        st = CH.new_game("doc", "pid", user_color="w")
        out["numbered"] = CH.play_opening(st, ["1. e4", "1... e5", "Nf3"]) + (st["fen"],)
        st = CH.new_game("doc", "pid", user_color="w")
        out["illegal"] = CH.play_opening(st, ["e5", "e4"]) + (st["fen"], len(st["history"]))
        st = CH.new_game("doc", "pid", user_color="b")
        out["squares"] = CH.play_opening(st, ["e2e4"]) + (st["fen"],)
        print(json.dumps(out))
    """)
    played, bad, fen, by = d["e4"]
    assert played == ["e4"] and bad is None and by == "user"
    assert fen.startswith("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b ")      # black to move
    assert d["numbered"][:2] == [["e4", "e5", "Nf3"], None]
    played, bad, fen, n = d["illegal"]
    assert played == [] and bad == "e5" and n == 0 and " w " in fen          # nothing played past it
    assert d["squares"][0] == ["e4"]


def test_a_new_game_plays_the_request_then_the_opponent_replies(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        seen = {}
        CH.setup_page = lambda doc, page_no, st, page_id=None: seen.setdefault("drawn", st["fen"])
        def engine_turn(doc, page_no, st, page_id=None, pick=None, **kw):
            seen.setdefault("replied_to", st["fen"])
            return {"ok": True, "san": "c5", "said": "", "feel": "neutral"}
        CH.engine_turn = engine_turn
        CH.save_state = lambda st: None
        GM.place_talk = lambda doc, page_no, st, talk, page_id=None, workdir=None: seen.setdefault("talk", talk)
        setup = {"user_color": "w", "profile": "a steady club player", "name": "Test", "elo": 1200,
                 "aggression": .5, "caution": .5, "risk": .3}
        GM.start_chess("doc", 3, "pid", setup, moves=["e4"])
        st2 = None
        GM.start_chess("doc", 3, "pid", dict(setup, user_color="w"), moves=None)
        print(json.dumps({k: (v if k != "talk" else [list(x)[:3] for x in v]) for k, v in seen.items()}))
    """)
    assert " b " in d["drawn"] and "4P3" in d["drawn"]                  # the board shows e4
    assert d["replied_to"] == d["drawn"]                                # and the opponent answers it
    assert any("From your request: 1. e4" in line[2] for line in d["talk"])


def test_the_squares_are_centered_and_the_labels_hang_outside_them(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import page as P
        out = {"safe": list(P.SAFE_AREA), "board": list(CH.BOARD_BOX), "talk": list(CH.talk_box()),
               "top": CH.TOP}
        st = CH.new_game("doc", "pid", user_color="w")
        bb = tuple(st["board"]["box"])
        m = CH.margin_of(st)
        out["margin"] = m
        out["a1"] = list(CH.square_box("a1", bb, False, m))
        out["h8"] = list(CH.square_box("h8", bb, False, m))
        out["e4"], out["e4_piece"] = list(CH.square_box("e4", bb, False, m)), list(CH.piece_box("e4", bb, False, m))
        out["e4_at"] = CH.square_at(*[(a + b) / 2 for a, b in zip(CH.piece_box("e4", bb, False, m)[:2],
                                                                  CH.piece_box("e4", bb, False, m)[2:])], board_box=bb)
        out["layer"] = list(CH.layer_box(bb, m))
        out["lower_row"] = list(CH.captured_box("b", 0, bb, "w", m))
        inside = {"board": {"box": list(bb), "margin": 0}}
        legacy = {"board": {"box": [-616.0, 512.0, 616.0, 1744.0]}}
        out["inside_margin"], out["legacy_margin"] = CH.margin_of(inside), CH.margin_of(legacy)
        out["legacy_a1"] = list(CH.square_box("a1", tuple(legacy["board"]["box"]), False, CH.LEGACY_MARGIN))
        out["legacy_piece"] = list(CH.piece_box("a1", tuple(legacy["board"]["box"]), False, CH.LEGACY_MARGIN))
        im = CH.board_image(False, 800)
        out["corners"] = [list(im.getpixel(p)) for p in ((50, 750), (150, 750), (50, 650))]   # a1, b1, a2
        out["green"], out["white"] = list(CH.GREEN), list(CH.WHITE)
        print(json.dumps(out))
    """)
    sx0, sy0, sx1, sy1 = d["safe"]
    bx0, by0, bx1, by1 = d["board"]
    assert d["top"] == sy0 and d["margin"] == -1
    assert abs((bx0 + bx1) / 2 - (sx0 + sx1) / 2) < 1e-6                # the squares are centered on the page
    assert abs((bx1 - bx0) - (by1 - by0)) < 1e-6
    lx0, ly0, lx1, ly1 = d["layer"]
    assert sx0 <= lx0 < bx0 and ly1 <= sy1 and lx1 == bx1                # the numbers hang to the left, inside the safe area
    assert d["lower_row"][1] >= by1 + 46                                 # the letters sit between the squares and the row
    assert d["talk"][0] == bx0 and d["talk"][1] == sy0
    assert d["a1"][0] == bx0 and abs(d["a1"][3] - by1) < 1e-6 and d["h8"][2] == bx1 and d["h8"][1] == by0
    sq, pc = d["e4"], d["e4_piece"]
    assert abs((sq[0] + sq[2]) - (pc[0] + pc[2])) < 1e-6 and abs((sq[1] + sq[3]) - (pc[1] + pc[3])) < 1e-6   # centered
    assert d["e4_at"] == "e4"
    assert d["inside_margin"] == 0 and d["legacy_margin"] == 48
    assert d["legacy_a1"][0] > -616.0 and d["legacy_piece"] == d["legacy_a1"]
    assert d["corners"][0] == d["green"] and d["corners"][1] == d["white"] and d["corners"][2] == d["white"]


def test_every_kind_of_content_starts_below_the_toolbar(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.host import layout as PL
        from paperdaemon.pipeline.games import messages as MS
        from paperdaemon.pipeline.games import adventure as AD
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import pdf as PD
        from PIL import Image
        out = {"safe": list(P.SAFE_AREA), "plan": list(PL.SAFE), "messages": MS.HEAD_TOP,
               "scene": list(AD.SCENE_BOX), "pdf_safe_top": PD.safe_top()}
        boxes = PL.solve([{"id": "a", "kind": "image", "size": "full", "near": "stack"},
                          {"id": "b", "kind": "chart", "size": "small", "near": "top-right"},
                          {"id": "c", "kind": "calendar", "size": "full", "near": "stack"}], first_free_y=0)
        out["placed_tops"] = [b["y0"] for b in boxes.values()]
        page = PD.page_image(Image.new("RGB", (600, 400), "black"), top=20)
        rows = [y for y in range(page.size[1]) if page.getpixel((page.size[0] // 2, y)) == (0, 0, 0)]
        out["pdf_first_row"] = rows[0]
        print(json.dumps(out))
    """)
    top = d["safe"][1]
    assert top >= 140                                              # the toolbar covers about the top 122 px
    assert d["plan"] == d["safe"]
    assert min(d["placed_tops"]) >= top
    assert d["messages"] >= top and d["scene"][1] >= top
    assert d["pdf_first_row"] >= d["pdf_safe_top"] > 100


def test_the_talk_strip_keeps_one_face_and_accepts_the_cast_marks(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline.games import cast as RCAST
        from paperdaemon.pipeline.charts import tabletop as TS
        lines = [["Buddy", "happy", "", [], None],
                 ["narrator", "", "Buddy plays Black at about 1100. Move a piece, or write your move."],
                 ["narrator", "", "From your request: 1. e4."],
                 ["Buddy", "happy", "", ["signature_1"], None],
                 ["narrator", "", "Buddy plays e5."]]
        kept = GM.talk_lines(lines)
        marked = GM.talk_lines([["Buddy", "sad", "", ["glint"], None], ["Buddy", "happy", "Hello!", [], None]])
        spoken = GM.talk_lines([["Buddy", "happy", "Hi there.", [], None], ["Buddy", "smug", "", [], None]])
        print(json.dumps({"kept": kept, "marked": len(marked), "spoken": len(spoken),
                          "schema_has_cast": all(m in TS.MARKS for m in RCAST.MARKS)}))
    """)
    assert [l[0] for l in d["kept"]] == ["narrator", "narrator", "Buddy", "narrator"]   # one face row
    assert d["kept"][2][3] == ["signature_1"]
    assert d["marked"] == 2 and d["spoken"] == 2         # a face with a mark or with words stays
    assert d["schema_has_cast"]                          # a signature mark no longer fails the strip


def test_a_talk_strip_too_small_to_read_quotes_its_earlier_speech(tmp_path):
    d = _run(tmp_path, """
        import os
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline.page import images as IM
        from PIL import Image
        work = os.path.join(os.environ["PAPERDAEMON_HOME"], "work")
        os.makedirs(work, exist_ok=True)

        def dialog_png(state, lines, out, width=None):       # a face row is tall, a line of text is not
            rows = sum(1 for l in lines if l[0] != "narrator")
            Image.new("RGB", (int(width), 260 * rows + 40 * (len(lines) - rows)), "white").save(out)
            return out
        GM.dialog_png = dialog_png
        IM.insert = lambda *a, **k: {"hash": "h", "name": "n", "doc": "d"}
        IM.record_placement = lambda *a, **k: None
        st = CH.new_game("doc", "pid", user_color="w")
        st["persona"]["name"] = 'Lyle "Buddy" Pruitt'
        talk = [('Lyle "Buddy" Pruitt', "happy", "Well, well, look who it is!", [], None),
                ("narrator", "", "From your request: 1. e4."),
                ('Lyle "Buddy" Pruitt', "happy", "Right on the nose, pal!", [], None)]
        GM.place_talk("doc", 1, st, talk, workdir=work)
        print(json.dumps({"lines": st["talk"]["lines"], "box": st["talk"]["box"]}))
    """)
    lines = d["lines"]
    assert [l[0] for l in lines] == ["narrator", "narrator", 'Lyle "Buddy" Pruitt']      # one face row left
    assert lines[0][2].endswith('"Well, well, look who it is!"')                          # its words kept
    x0, y0, x1, y1 = d["box"]
    assert abs((y1 - y0) - 290) < 1 and (x1 - x0) / 1526 >= 0.55         # the strip at a readable scale


def test_writing_on_a_game_page_comes_off_only_once_it_was_read(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import render as R
        erased, out = [], {}
        st = CH.new_game("doc", "pid", user_color="w")
        GM.game_on_page = lambda doc, page_id: dict(st)
        P.record = lambda *a, **k: None
        P.erase = lambda doc, page_no, which: erased.append(page_no)
        R.strokes = lambda doc, page_no: ["a stroke"]
        R.render = lambda doc, page_no, png: None
        CH.user_turn = lambda doc, page_no, state, page_id: {"ok": True}
        CH.tidy = CH.save_state = lambda *a, **k: None
        GM.place_talk = lambda *a, **k: None
        GM._remember_turn = lambda *a, **k: None
        GM._remark = lambda state, context, ask_text, log: []
        for kind, reading in (("unclear", {"kind": "unclear", "raw": "?"}), ("nothing", {"kind": "nothing", "raw": ""}),
                              ("say", {"kind": "say", "raw": "hello", "text": "hello"})):
            GM.read_writing = lambda state, png, ask_vision, r=reading: r
            del erased[:]
            GM.play("doc", 3, "pid", ask_vision=lambda *a, **k: "")
            out[kind] = len(erased)
        del erased[:]
        GM.play("doc", 3, "pid", ask_vision=None)                   # no vision model: nothing can be read
        out["blind"] = len(erased)
        print(json.dumps(out))
    """)
    assert d == {"unclear": 0, "nothing": 0, "say": 1, "blind": 0}
