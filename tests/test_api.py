import json
import os
import uuid

from fastapi.testclient import TestClient

from paperdaemon import harnesses, loop, notepad, paths, server, settings


def client():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    return c


def test_every_api_request_needs_the_pairing_token():
    c = TestClient(server.app)
    r = c.get("/api/v1/status")
    assert r.status_code == 401 and r.json() == {"error": "not paired"}
    r = c.get("/api/v1/status", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert client().get("/api/v1/status").status_code == 200


def host():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.host_token()
    return c


def test_the_host_surface_needs_the_host_token():
    assert TestClient(server.app).get("/host/status").status_code == 401
    assert client().get("/host/status").status_code == 401             # the pairing token opens the API only
    assert TestClient(server.app).get("/host/llm/wrong/health").status_code == 401
    assert host().get("/host/status").status_code == 200
    assert host().get("/api/v1/status").status_code == 401              # and the host token the host's surface only


def test_routes_are_versioned_and_no_docs_are_served():
    c = client()
    assert c.get("/api/settings").status_code == 404
    assert c.get("/api/v1/settings").status_code == 200
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_rotation_refuses_the_old_token():
    c = client()
    old = server.pairing_token()
    new = c.post("/api/v1/pairing/rotate").json()["token"]
    assert new != old
    assert TestClient(server.app).get("/api/v1/status", headers={"Authorization": "Bearer " + old}).status_code == 401
    assert TestClient(server.app).get("/api/v1/status", headers={"Authorization": "Bearer " + new}).status_code == 200


def test_status_reports_the_loop_the_lineup_and_the_first_run():
    d = client().get("/api/v1/status").json()
    assert d["lineup"] == "Qwen 3.8 + Klein" and d["first_run"] is True
    assert d["loop"]["running"] is False and set(d["loop"]["halves"]) == {"daemon", "host"}


def test_settings_report_secrets_as_flags_only():
    c = client()
    c.put("/api/v1/keys/text", json={"where": "https://api.anthropic.com", "value": "sk-flag-test-000000000"})
    c.put("/api/v1/keys/search", json={"where": "brave", "value": "sk-flag-test-111111111"})
    d = c.get("/api/v1/settings").json()
    assert d["secrets"]["keys"] == ["key:search:brave", "key:text:api.anthropic.com"]
    assert "sk-flag-test" not in str(d)


def test_invalid_settings_answer_400_with_the_reason():
    c = client()
    s = c.get("/api/v1/settings").json()["settings"]
    s["lineups"][0]["tags"] = [{"name": "ignore", "prompt": ""}]
    r = c.put("/api/v1/settings", json=s)
    assert r.status_code == 400 and "cannot also be the ignore tag" in r.json()["error"]


def test_lineups_create_update_delete_and_every_one_is_live():
    c = client()
    d = c.get("/api/v1/lineups").json()
    assert d["in_use"] is None and len(d["lineups"]) == 2 and "active" not in d
    body = {"text": {"location": "http://127.0.0.1:9100", "script": "my-text.bat", "harness": "auto"},
            "image": {"location": "", "script": "", "harness": "auto"}, "tags": [{"name": "Small", "prompt": "Be brief."}]}
    d = c.put("/api/v1/lineups/Small", json=body).json()
    assert [lu["name"] for lu in d["lineups"]][-1] == "Small"
    d = c.put("/api/v1/lineups/Small", json={"text": {"harness": "default-text"}}).json()
    small = [lu for lu in d["lineups"] if lu["name"] == "Small"][0]
    assert small["text"]["harness"] == "default-text" and small["text"]["script"] == "my-text.bat"
    assert small["tags"] == [{"name": "Small", "prompt": "Be brief."}]          # tags kept when not sent
    r = c.put("/api/v1/lineups/Small", json={"image": {"harness": "qwen3.6-27b"}})
    assert r.status_code == 400 and "not a image harness" in r.json()["error"]
    r = c.put("/api/v1/lineups/Qwen 3.6 + Klein", json={"tags": [{"name": "small", "prompt": ""}]})
    assert r.status_code == 400 and "already" in r.json()["error"]            # a tag is one lineup's only
    assert c.post("/api/v1/lineups/Small/activate").status_code in (404, 405)  # there is no active lineup
    d = c.delete("/api/v1/lineups/Small").json()
    assert "Small" not in [lu["name"] for lu in d["lineups"]]


def test_a_renamed_lineup_keeps_its_memories_and_a_deleted_one_loses_them():
    from paperdaemon import memories
    c = client()
    memories.add("Qwen 3.8 + Klein", "Erase my request once it is answered.")
    d = c.put("/api/v1/lineups/Qwen 3.8 + Klein", json={"name": "Everyday"}).json()
    assert d["lineups"][0]["name"] == "Everyday"
    got = c.get("/api/v1/lineups/Everyday/memories").json()
    assert [m["text"] for m in got["memories"]] == ["Erase my request once it is answered."] and got["max"] == 30
    mid = got["memories"][0]["id"]
    got = c.put("/api/v1/lineups/Everyday/memories/" + mid, json={"text": "Erase the request when done."}).json()
    assert got["memories"][0]["text"] == "Erase the request when done."
    c.delete("/api/v1/lineups/Everyday")
    assert memories.of("Everyday") == []


def test_the_host_names_the_lineup_of_each_job():
    c = client()
    tok = server.host_token()
    r = c.post("/host/lineup", json={"name": "Qwen 3.6 + Klein"}, headers={"Authorization": "Bearer " + tok})
    assert r.json() == {"in_use": "Qwen 3.6 + Klein"}
    assert settings.active()["name"] == "Qwen 3.6 + Klein"
    assert c.post("/host/lineup", json={"name": "Nothing"}, headers={"Authorization": "Bearer " + tok}).status_code == 404
    settings.use(None)


def test_start_scripts_live_in_the_lineup_and_none_ship():
    from paperdaemon import scripts
    c = client()
    assert c.get("/api/v1/scripts").status_code == 404            # no screen of its own: a lineup's slot holds its script
    assert os.listdir(scripts.folder()) == []


def test_harnesses_are_listed_with_their_fields():
    with open(os.path.join(harnesses.user_folder(), "llm", "bad.json"), "w") as f:
        f.write("{not json")
    d = client().get("/api/v1/harnesses").json()
    by = {p["id"]: p for p in d if p.get("id")}
    assert by["qwen3.8-27b"]["kind"] == "text" and by["qwen3.8-27b"]["extends"] == "default-text"
    assert "context" not in by["qwen3.8-27b"]["fields"] and "thinking" not in by["qwen3.8-27b"]["fields"]
    assert by["flux.2-klein-9b"]["fields"]["steps"] == 4
    assert by["flux.2-klein-9b"]["fields"]["workflows"]["childrensColoringBook"]["steps"] == 12
    assert "edit_reference" in by["flux.2-klein-9b"]["fields"]["abilities"]
    assert "edit_reference" not in by["z-image-turbo"]["fields"]["abilities"]
    assert by["default-text"]["extends"] is None
    broken = [p for p in d if p.get("error")]
    assert len(broken) == 1 and broken[0]["file"] == os.path.join("llm", "bad.json")


def test_models_describe_the_active_lineup():
    import socket
    with socket.socket() as sk:                     # a port of its own: nothing answers there
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    s = settings.load()
    settings.active(s)["text"]["location"] = "http://127.0.0.1:%d" % port
    settings.save(s)
    c = client()
    d = c.get("/api/v1/models").json()
    assert d["lineup"] == "Qwen 3.8 + Klein"
    assert d["text"]["harness"]["name"] == "llama.cpp - Qwen 3.8 27B" and d["text"]["harness"]["how"] == "user"
    assert d["text"]["capabilities"]["vision"]["value"] is True
    assert d["image"]["harness"]["name"] == "stable-diffusion.cpp - FLUX.2 Klein 9B"
    assert d["text"]["server"]["answering"] is False and d["text"]["server"]["started_by_paperdaemon"] is False


def _ledger(entries):
    with open(os.path.join(paths.data_dir(), "rm-ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": entries}, f)


DOC = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://paperdaemon.invalid/test-notebook"))


def test_jobs_come_from_the_ledger_newest_first():
    _ledger({"aaaaaaaa/bbbbbbbb": {"doc": "Notes", "doc_id": DOC, "page": 2, "status": "done", "note": "answered",
                                   "first_seen": 100, "claim_at": 110, "completed_at": 150},
             "cccccccc/dddddddd": {"doc": "Notes", "doc_id": DOC, "page": 3, "status": "working", "note": "",
                                   "first_seen": 200, "claim_at": 210},
             "eeeeeeee/ffffffff": {"doc": "Old", "doc_id": DOC, "page": 1, "status": "skipped",
                                   "note": "baselined: there before", "first_seen": 50}})
    d = client().get("/api/v1/jobs?limit=10").json()
    assert [j["key"] for j in d] == ["cccccccc/dddddddd", "aaaaaaaa/bbbbbbbb"]
    assert d[1] == {"key": "aaaaaaaa/bbbbbbbb", "notebook": "Notes", "doc_id": DOC, "page": 2, "status": "done",
                    "note": "answered", "failed": False, "started": 110, "finished": 150, "lineup": None, "tag": ""}
    assert d[0]["finished"] is None


def test_notepads_are_listed_read_and_wiped():
    folder = notepad.folder()
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, DOC + ".md"), "w", encoding="utf-8") as f:
        f.write("## 10:00, page id x\n- note: a\n\n## 11:00, page id y\n- note: b\n\n")
    with open(os.path.join(paths.mirror_dir(), DOC + ".metadata"), "w", encoding="utf-8") as f:
        json.dump({"visibleName": "Garden notes"}, f)
    c = client()
    d = c.get("/api/v1/notepads").json()
    assert d == [{"doc": DOC, "notebook": "Garden notes", "entries": 2, "chars": d[0]["chars"]}] and d[0]["chars"] > 40
    assert "note: b" in c.get("/api/v1/notepads/" + DOC).json()["text"]
    assert c.post("/api/v1/notepads/" + DOC + "/wipe").json() == {"wiped": 2}
    assert c.get("/api/v1/notepads").json() == []
    assert c.post("/api/v1/notepads/not-an-id/wipe").status_code == 404


def test_a_notepad_is_not_wiped_while_a_job_works():
    _ledger({"aaaaaaaa/bbbbbbbb": {"doc_id": DOC, "status": "working"}})
    r = client().post("/api/v1/notepads/" + DOC + "/wipe")
    assert r.status_code == 409


def test_the_benchmark_lists_its_cases():
    d = client().get("/api/v1/tests").json()
    assert d["result"] is None and d["changed"] is False
    assert [r["id"] for r in d["plan"]][:2] == ["model-text", "model-image"]
    assert {"answer", "ink", "chart", "draw", "picture"} <= {r["id"] for r in d["plan"]}
    assert client().get("/api/v1/tests/status").json()["running"] is False
    assert client().post("/api/v1/tests/run", json={"lineup": "Nothing"}).status_code == 404


def test_the_desktop_token_is_reused_when_found(monkeypatch, fresh):
    from paperdaemon.remarkable import auth, desktop_token
    monkeypatch.setattr(desktop_token, "find", lambda: None)
    assert client().post("/api/v1/tablet/desktop-token").json() == {"found": False, "set": False}
    monkeypatch.setattr(desktop_token, "find", lambda: "@ByteArray(header.e30.sig)")
    assert client().post("/api/v1/tablet/desktop-token").json() == {"found": True, "set": True}
    assert fresh.get_password("PaperDaemon", auth.DEVICE_KEY) == "header.e30.sig"


def test_the_host_loads_lazily_and_reads_the_status():
    c = host()
    assert c.post("/host/load", json={"key": "image"}).json()["key"] == "image"
    st = c.get("/host/status").json()
    assert st["key"] == "image" and st["phase"] == "ready" and st["tablet"] == {"image": "image"}
    assert st["loaded"]["harness"] == "flux.2-klein-9b"
    assert c.post("/host/load", json={"key": "nothing"}).status_code == 400
    assert c.get("/host/image/none.png").status_code == 404


def test_the_text_proxy_reports_health_by_the_engine_rule():
    c = host()
    # the shipped lineup has a start script, so a call would be served (the script starts the server)
    assert c.get("/host/llm/%s/health" % server.host_token()).json() == {"status": "ok"}
    s = settings.load()
    settings.active(s)["text"].update(script="", location="http://127.0.0.1:9")    # nothing listens there
    settings.save(s)
    assert c.get("/host/llm/%s/health" % server.host_token()).status_code == 503


def test_a_notepad_comes_back_in_parts():
    from paperdaemon import notepad as NP
    pad = NP.Notepad(DOC)
    pad.append("abcdef12", ["asked: draw an owl", "done: drew it", "on the page: an owl in place 1"])
    got = client().get("/api/v1/notepads/" + DOC).json()["entries"]
    assert got[0]["asked"] == ["draw an owl"] and got[0]["did"] == ["done: drew it", "an owl in place 1"]
    assert got[0]["page_id"] == "abcdef12" and got[0]["page"] is None and len(got[0]["when"]) == 16
