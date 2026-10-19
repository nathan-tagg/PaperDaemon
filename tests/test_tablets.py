"""Every tablet's page: the frame a page carries says which tablet made it (Paper Pro 1620 x 2160, Paper Pro Move
954 x 1696, reMarkable 2 and Paper Pure 1404 x 1872), and what PaperDaemon puts on a page follows that frame."""
from paperdaemon.pipeline.page import tablets as TB


def test_a_page_is_known_by_its_frame():
    assert TB.of_frame((1620, 2160))["name"] == "Paper Pro" and TB.of_frame((1620.0, 2160.0))["color"]
    assert TB.of_frame((954, 1696))["name"] == "Paper Pro Move"
    mono = TB.of_frame((1404, 1872))
    assert "Paper Pure" in mono["name"] and not mono["color"]
    assert TB.of_frame((1240, 1754)) is None                        # a PDF page at its own size is no tablet's


def test_the_model_is_told_the_pages_own_coordinates():
    assert "x from -477 to 477" in TB.coordinates((954, 1696)) and "1696" in TB.coordinates((954, 1696))
    # a frame never claims a tablet: the user's Paper Pro wrote a 1404 x 1872 page
    assert all("gray" not in TB.coordinates(f) and "Paper" not in TB.coordinates(f) for f in ((1404, 1872), (1620, 2160)))


def test_a_page_drawn_as_one_picture_fits_every_tablet():
    box, s = TB.picture_page((1404, 1872))
    assert box == (-702.0, 0.0, 702.0, 1872.0) and abs(s - 1404 / 1620.0) < 1e-9      # exactly the page: 3:4 too
    box, s = TB.picture_page((954, 1696))
    assert box[0] == -477.0 and box[2] == 477.0 and box[3] <= 1696                     # the Move: its width, from the top


def test_a_chess_board_fits_the_page_it_is_on(monkeypatch):
    from paperdaemon.pipeline import page as P
    from paperdaemon.pipeline.games import chess as CH
    from paperdaemon.pipeline.page import render as R
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "p1"}])
    for frame in ((1620, 2160), (1404, 1872), (954, 1696)):
        monkeypatch.setattr(R, "page_frame", lambda doc, n, f=frame: f)
        box, top = CH.page_board("d", "p1")
        safe = P.safe_area(frame)
        assert safe[0] <= box[0] - CH.LABEL_W and box[2] <= safe[2] and top == safe[1]       # inside, labels too
        assert box[3] + CH.LABEL_H + CH.CAP_GAP + CH.CAP <= safe[3] + 1e-6
        assert abs((box[2] - box[0]) - (box[3] - box[1])) < 1e-6                              # still square


def test_the_daemons_note_sits_at_its_pages_own_foot():
    from paperdaemon.pipeline.draw import signature as SIG
    assert SIG.footer_baseline() == SIG.FOOTER_Y                                             # a Paper Pro page, as before
    y = SIG.footer_baseline(frame=(1404, 1872))
    assert y == 1872 - (SIG.PAGE_BOTTOM - SIG.FOOTER_Y) and SIG._gutter((1404, 1872))[2] == -702 + 120


def test_the_devices_the_service_names_are_kept_as_seen(tmp_path, monkeypatch):
    import json
    from paperdaemon import paths
    from paperdaemon.remarkable import sync
    monkeypatch.setattr(paths, "state_dir", lambda: str(tmp_path))
    sync.note_device({"event": "SyncComplete", "sourceDeviceID": "tablet-a", "sourceDeviceDesc": "remarkable"})
    sync.note_device({"event": "SyncComplete", "sourceDeviceID": "tablet-a", "sourceDeviceDesc": "remarkable"})
    sync.note_device({"event": "DocAdded", "sourceDeviceID": "app-b", "sourceDeviceDesc": "desktop-windows",
                      "deviceName": "Laptop"})
    seen = json.load(open(tmp_path / "devices-seen.json"))
    assert seen["tablet-a"]["events"] == 2 and seen["tablet-a"]["desc"] == "remarkable"
    assert seen["app-b"]["name"] == "Laptop" and "deviceName" in seen["app-b"]["fields"]
