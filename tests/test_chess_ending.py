"""The end of a chess game: the opponent stays at the table and has the last word, a turn with no line of theirs keeps
their face, and a finished game takes no more moves. The pipeline reads where its files are when it is imported, so
its modules run in a process of their own."""
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


def test_the_opponent_has_the_last_word_when_the_game_ends_on_the_players_move(tmp_path):
    # the player mates on their own move: the opponent has no move to make, and their strip used to go with them
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import render as R
        from paperdaemon.pipeline.games import inputarea as IA
        st = CH.new_game("doc", "pid", user_color="b",
                         fen="rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2")
        st["persona"].update({"name": "Barty Tusk", "character": "barty-tusk"})
        placed, asked = [], []
        GM.game_on_page = lambda doc, page_id: st
        P.record = lambda *a, **k: None
        R.strokes = lambda doc, page_no: []
        IA.typed = lambda doc, page_no: ""

        def user_turn(doc, page_no, state, page_id):
            change = CH.apply_move(state, "d8h4")
            return {"ok": True, "uci": "d8h4", "san": change["san"]}
        CH.user_turn = user_turn
        CH.tidy = CH.save_state = lambda *a, **k: None
        GM.place_talk = lambda doc, page_no, state, lines, page_id=None, workdir=None: placed.append(
            [list(l) for l in lines])
        GM._remember_turn = lambda *a, **k: None

        def model(prompt):
            asked.append(prompt)
            return "SAY: Well played. I never saw the queen coming.\\nFEEL: sad 6\\nTRUTH: true\\nFACE: none"
        out = GM.play("doc", 1, "pid", ask_text=model)
        print(json.dumps({"out": out, "placed": placed, "asked": asked, "status": st["status"]}))
    """)
    assert d["status"] == "checkmate" and d["out"][0] == "done"
    said = [l for l in d["placed"][0] if l[0] == "Barty Tusk"]
    assert said and said[0][2] == "Well played. I never saw the queen coming." and said[0][1]   # words and a face
    assert len(d["asked"]) == 1
    assert "THE GAME IS OVER: the player checkmated you with Qh4#; the player won." in d["asked"][0]
    assert "lost" in d["asked"][0]                        # the table moved their feelings with the result


def test_without_a_model_the_face_stays_and_an_opponent_without_one_says_its_words(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        st = CH.new_game("doc", "pid", user_color="w")
        st["persona"].update({"name": "Barty Tusk", "character": "barty-tusk"})
        st["status"], st["result"] = "resigned", "0-1"
        quiet = GM._farewell(st, None)
        plain = CH.new_game("doc", "pid", user_color="w", persona="a steady club player")
        plain["status"], plain["result"] = "stalemate", "1/2-1/2"
        words = GM._farewell(plain, lambda prompt: "SAY: A draw, then. Good game.")
        mute = GM._farewell(plain, None)
        print(json.dumps({"quiet": [list(l) for l in quiet], "words": [list(l) for l in words], "mute": mute,
                          "resigned": CH.ended(st), "stalemate": CH.ended(plain)}))
    """)
    face = [l for l in d["quiet"] if l[0] == "Barty Tusk"]
    assert face and face[0][1] and not face[0][2]         # their face, in the mood the end left them in
    assert d["words"] == [["Opponent", "neutral", "A draw, then. Good game."]] and d["mute"] == []
    assert d["resigned"] == "the player resigned; you won." and d["stalemate"] == "a draw, by stalemate."


def test_the_opponents_face_stays_when_a_turn_has_no_line_of_theirs(tmp_path):
    d = _run(tmp_path, """
        import os
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline.page import images as IM
        from PIL import Image
        work = os.path.join(os.environ["PAPERDAEMON_HOME"], "work")
        os.makedirs(work, exist_ok=True)
        drawn, removed = [], []

        def dialog_png(state, lines, out, width=None):
            drawn.append([list(l) for l in lines])
            Image.new("RGB", (int(width), 300), "white").save(out)
            return out
        GM.dialog_png = dialog_png
        IM.insert = lambda *a, **k: {"hash": "h", "name": "n", "doc": "d"}
        IM.record_placement = lambda *a, **k: None
        IM.remove_in_box = lambda *a, **k: removed.append(1)
        st = CH.new_game("doc", "pid", user_color="w")
        st["persona"].update({"name": "Barty Tusk", "character": "barty-tusk"})
        GM.place_talk("doc", 1, st, [("Barty Tusk", "smug", "Your move.", ["glint"], None)], workdir=work)
        refused = [("narrator", "", "Not legal: a knight cannot move from g1 to g3. The piece went back.")]
        GM.place_talk("doc", 1, st, refused, workdir=work)
        kept = st["talk"]["lines"]
        again = GM.place_talk("doc", 1, st, refused, workdir=work)
        print(json.dumps({"kept": kept, "drawn": len(drawn), "removed": len(removed), "again": bool(again)}))
    """)
    assert d["kept"] == [["Barty Tusk", "smug", "", [], None]]    # the face, without the words or the passing tell
    assert d["drawn"] == 2 and d["removed"] == 1                 # the same face is not drawn over again
    assert d["again"]


def test_a_finished_game_takes_no_more_moves(tmp_path):
    # after a resignation the board still has legal moves: one written afterward went into the finished game
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        st = CH.new_game("doc", "pid", user_color="w")
        st["status"], st["result"] = "resigned", "0-1"
        try:
            CH.apply_move(st, "e2e4")
            applied = True
        except ValueError:
            applied = False
        written = CH.play_user_uci("doc", 1, st, "e2e4", "pid")
        seen = {pid: {"square": p["square"]} for pid, p in st["pieces"].items()}
        still = CH.infer_move(st, dict(seen))
        pawn = next(pid for pid, p in st["pieces"].items() if p["square"] == "e2")
        seen[pawn] = {"square": "e4"}
        dragged = CH.infer_move(st, seen)
        print(json.dumps({"applied": applied, "written": written, "still": still, "dragged": dragged,
                          "history": len(st["history"])}))
    """)
    assert not d["applied"] and d["history"] == 0
    assert d["written"]["ok"] is False and "over" in d["written"]["reason"]
    assert d["still"] == {"ok": True, "uci": None}       # nothing moved after the game is no move, not a refusal
    assert d["dragged"]["ok"] is False and "over" in d["dragged"]["reason"]
