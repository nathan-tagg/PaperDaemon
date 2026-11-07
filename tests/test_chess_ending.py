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


def test_a_draw_offer_is_answered_in_the_opponents_own_voice(tmp_path):
    # a fixed "A draw? Fine by me." was every character's answer, whoever they were
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import render as R
        from paperdaemon.pipeline.games import inputarea as IA
        out = {}
        for case, cp in (("taken", 200), ("refused", -200)):
            st = CH.new_game("doc", "pid", user_color="w")
            st["persona"].update({"name": "Barty Tusk", "character": "barty-tusk"})
            placed = []
            GM.game_on_page = lambda doc, page_id, st=st: st
            P.record = P.erase_text = lambda *a, **k: None
            R.strokes = lambda doc, page_no: []
            IA.typed = lambda doc, page_no: "Draw?"

            class Eng(object):
                def __init__(self, elo):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def candidates(self, fen, multipv=1, cp=cp):
                    return [{"cp": cp}]
            CH.Engine = Eng
            CH.user_turn = lambda doc, page_no, state, page_id: {"ok": True, "uci": None}
            CH.tidy = CH.save_state = lambda *a, **k: None
            GM.place_talk = lambda doc, page_no, state, lines, page_id=None, workdir=None, placed=placed: placed.append(
                [list(l) for l in lines])
            GM._remember_turn = lambda *a, **k: None

            def model(prompt, case=case):
                if "What does it say?" in prompt:
                    return "DRAW"
                return ("SAY: A draw it is, friend. Honors even.\\nFEEL: relieved 5" if case == "taken" else
                        "SAY: Oh no, not while I hold the open file.\\nFEEL: smug 6")
            GM.play("doc", 1, "pid", ask_text=model)
            out[case] = {"status": st["status"], "said": [l[2] for l in placed[0] if l[0] == "Barty Tusk"]}
        print(json.dumps(out))
    """)
    assert d["taken"]["status"] == "draw_agreed" and d["taken"]["said"] == ["A draw it is, friend. Honors even."]
    assert d["refused"]["status"] == "playing" and d["refused"]["said"] == ["Oh no, not while I hold the open file."]


def test_a_move_that_is_not_legal_is_refused_by_the_opponent_and_named_in_the_receipt(tmp_path):
    # "Ke3" typed with the king on e1 was passed over in silence: "nothing new on the page", the typed move left there
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import render as R
        from paperdaemon.pipeline.games import inputarea as IA
        st = CH.new_game("doc", "pid", user_color="w")
        st["persona"].update({"name": "Barty Tusk", "character": "barty-tusk"})
        placed, erased, asked = [], [], []
        GM.game_on_page = lambda doc, page_id: st
        P.record = lambda *a, **k: None
        P.erase_text = lambda *a, **k: erased.append(1)
        R.strokes = lambda doc, page_no: []
        IA.typed = lambda doc, page_no: "Ke3"
        CH.user_turn = lambda doc, page_no, state, page_id: {"ok": True, "uci": None}
        CH.tidy = CH.save_state = lambda *a, **k: None
        GM.place_talk = lambda doc, page_no, state, lines, page_id=None, workdir=None: placed.append(
            [list(l) for l in lines])
        GM._remember_turn = lambda *a, **k: None

        def model(prompt):
            asked.append(prompt)
            if "What does it say?" in prompt:
                return "MOVE: Ke3"
            return "SAY: Your king doesn't jump, friend. Try again.\\nFEEL: amused 4"
        out = GM.play("doc", 1, "pid", ask_text=model)
        print(json.dumps({"out": out, "placed": placed, "erased": len(erased), "asked": asked[-1],
                          "history": len(st["history"]), "plain": [GM._plain(s) for s in ("*Baa.*", "I **win**", "a*b")]}))
    """)
    assert d["out"][0] == "done" and "not played: Ke3 is not a legal move here" in d["out"][1]
    said = [l[2] for l in d["placed"][0] if l[0] == "Barty Tusk"]
    assert said == ["Your king doesn't jump, friend. Try again."]
    assert d["erased"] == 1 and d["history"] == 0              # the typed move came off; nothing was played
    assert "Ke3" in d["asked"] and "not a legal move" in d["asked"]
    assert d["plain"] == ["Baa.", "I win", "a*b"]
