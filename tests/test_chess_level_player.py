"""The one who plays for a level game (the maintainer's word, 11-07): "a cast member who always plays the top stockfish
engine move that moves the evaluation to even ... He doesn't say this out loud though ... and if you offer him a draw
he'll accept immediately." His profile says so (games.chess "aims_for": "even", "draw_offers": "accepts"); the game
carries it out. The pipeline reads where its files are when it is imported, so its modules run in a process of their
own."""
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
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN", "PAPERDAEMON_CONTENT"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_move_nearest_even_is_his_whoever_is_ahead(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        c = lambda san, cp, mate=None: {"san": san, "cp": cp, "mate": mate}
        print(json.dumps({
            "ahead": CH.level_move([c("Qxd8", 900), c("Nf3", 310), c("Rd1", 40), c("Bg5", -40)])["san"],
            "behind": CH.level_move([c("Kf1", -120), c("Kg1", -260), c("Qh5", -900)])["san"],
            "tie": CH.level_move([c("e4", 30), c("d4", -30)])["san"],
            "mate": CH.level_move([c("Qh7#", 32000, 1), c("Qxf7", 2500), c("Kh1", 60)])["san"],
            "none": CH.level_move([]),
        }))
    """)
    # ahead, he gives the advantage back; behind, he plays the best defense; of two as near, the engine's higher-ranked;
    # a mate is as far from even as a score gets
    assert d == {"ahead": "Rd1", "behind": "Kf1", "tie": "e4", "mate": "Kh1", "none": None}


def test_his_profile_says_how_he_plays_and_the_others_play_to_win(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH, characters as RC
        st = CH.new_game("doc", "pid", user_color="w")
        out = {"errors": RC.roster_errors(), "brief": RC.brief("ambrose-tull", game="chess")}
        for cid in ("ambrose-tull", "vera-novak"):
            st["persona"].update({"name": RC.get(cid)["name"], "character": cid})
            out[cid] = [CH.aims(st), CH.takes_draws(st)]
        print(json.dumps(out))
    """)
    assert d["errors"] == []
    assert d["ambrose-tull"] == ["even", True] and d["vera-novak"] == [None, False]
    # the model playing him knows why he plays as he does, and that he never says it
    assert "PRIVATE SECRET" in d["brief"] and "draw" in d["brief"] and "never" in d["brief"]


def test_he_plays_the_move_nearest_even_and_a_model_playing_him_is_shown_that_move_alone(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        st = CH.new_game("doc", "pid", user_color="b")
        st["persona"].update({"name": "Ambrose Tull", "character": "ambrose-tull"})
        asked, pvs = [], []

        class Eng(object):
            def candidates(self, fen, multipv=None, depth=None):
                pvs.append(multipv)
                feats = {"capture": False, "captured_value": 0, "check": False, "castling": False, "promotion": False,
                         "forward": 1, "king_zone": 0, "hanging": False, "defended": True, "piece": "P", "reply": ""}
                return [dict(feats, uci="e2e4", san="e4", cp=60, mate=None, loss=0),
                        dict(feats, uci="d2d4", san="d4", cp=45, mate=None, loss=15),
                        dict(feats, uci="g2g4", san="g4", cp=-5, mate=None, loss=65),
                        dict(feats, uci="f2f3", san="f3", cp=-50, mate=None, loss=110)]
        CH._finish = lambda *a, **k: None

        def model(prompt):
            asked.append(prompt)
            return "MOVE: e4\\nSAY: Well. Let's see how it goes.\\nFEEL: thinking 4"
        r = CH.engine_turn("doc", 1, st, "pid", pick=model, engine=Eng())
        print(json.dumps({"san": r["san"], "pv": pvs, "shown": [s for s in ("e4", "d4", "g4", "f3") if s in asked[-1]]}))
    """)
    assert d["san"] == "g4"                               # the move nearest even, not the best (e4)
    assert d["pv"] == [32]                                # enough of the engine's moves to find it
    assert d["shown"] == ["g4"]                           # the model saying his lines is shown that move alone


def test_he_takes_a_draw_the_moment_it_is_offered(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import chess as CH
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline import page as P
        from paperdaemon.pipeline.page import render as R
        from paperdaemon.pipeline.games import inputarea as IA
        st = CH.new_game("doc", "pid", user_color="w")
        st["persona"].update({"name": "Ambrose Tull", "character": "ambrose-tull"})
        st["strength"]["elo"] = 2300                      # strong, in the opening: anyone else would refuse
        placed = []
        GM.game_on_page = lambda doc, page_id: st
        P.record = P.erase_text = lambda *a, **k: None
        R.strokes = lambda doc, page_no: []
        IA.typed = lambda doc, page_no: "Draw?"

        class Eng(object):
            def __init__(self, elo):
                raise AssertionError("the board was looked at: he takes any draw, whatever it shows")
        CH.Engine = Eng
        CH.user_turn = lambda doc, page_no, state, page_id: {"ok": True, "uci": None}
        CH.tidy = CH.save_state = lambda *a, **k: None
        GM.place_talk = lambda doc, page_no, state, lines, page_id=None, workdir=None: placed.append([list(l) for l in lines])
        GM._remember_turn = lambda *a, **k: None

        def model(prompt):
            if "What does it say?" in prompt:
                return "DRAW"
            return "SAY: Well. A fair result.\\nFEEL: relieved 5"
        GM.play("doc", 1, "pid", ask_text=model)
        print(json.dumps({"status": st["status"], "result": st["result"],
                          "said": [l[2] for l in placed[0] if l[0] == "Ambrose Tull"]}))
    """)
    assert d["status"] == "draw_agreed" and d["result"] == "1/2-1/2"
    assert d["said"] == ["Well. A fair result."]
