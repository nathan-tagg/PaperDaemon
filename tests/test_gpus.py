"""The card PaperDaemon draws with, and what the window's web view is started with for it."""
from paperdaemon import gpus

XTX = {"name": "big", "vendor": 4098, "device": 1, "memory": 24 << 30, "luid": [0, 82318], "d3d12": True, "d3d11": True}
IGPU = {"name": "small", "vendor": 4098, "device": 2, "memory": 512 << 20, "luid": [0, 95712], "d3d12": True, "d3d11": True}
OLD = {"name": "old", "vendor": 32902, "device": 3, "memory": 2 << 30, "luid": [1, 7], "d3d12": False, "d3d11": True}
NONE = {"name": "none", "vendor": 1, "device": 4, "memory": 8 << 30, "luid": [0, 9], "d3d12": False, "d3d11": False}


def test_the_direct3d_12_card_with_the_most_memory_is_chosen(monkeypatch):
    monkeypatch.delenv("PAPERDAEMON_WEBGPU_D3D11", raising=False)
    assert gpus.chosen([IGPU, XTX]) is XTX
    assert gpus.chosen([OLD, IGPU]) is IGPU          # Direct3D 12 first, however much memory the other has
    assert gpus.chosen([NONE, OLD]) is OLD
    assert gpus.chosen([NONE]) is None and gpus.chosen([]) is None


def test_the_window_is_told_its_card_and_direct3d_11_when_the_card_has_no_12(monkeypatch):
    monkeypatch.delenv("PAPERDAEMON_WEBGPU_D3D11", raising=False)
    assert gpus.window_args([XTX]) == []                                     # one card with 12: as WebView2 ships
    assert gpus.window_args([IGPU, XTX]) == ["--use-adapter-luid=0,82318"]
    assert gpus.window_args([OLD]) == gpus.D3D11_ARGS
    assert gpus.window_args([NONE, OLD]) == ["--use-adapter-luid=1,7"] + gpus.D3D11_ARGS
    assert gpus.window_args([NONE]) == [] and gpus.window_args([]) == []     # no card: the processor


def test_direct3d_11_can_be_asked_for_on_a_card_with_12(monkeypatch):
    monkeypatch.setenv("PAPERDAEMON_WEBGPU_D3D11", "1")
    assert gpus.window_args([XTX]) == gpus.D3D11_ARGS


def test_the_processor_starts_the_window_with_no_card(monkeypatch):
    monkeypatch.delenv("PAPERDAEMON_WEBGPU_D3D11", raising=False)
    assert gpus.window_args([IGPU, XTX], processor=True) == gpus.CPU_ARGS          # whatever cards there are
    assert gpus.window_args([OLD], "1:2:0", processor=True) == gpus.CPU_ARGS


def test_the_window_follows_the_settings(monkeypatch):
    monkeypatch.delenv("PAPERDAEMON_WEBGPU_D3D11", raising=False)
    monkeypatch.setattr(gpus, "cards", lambda: gpus.named([dict(IGPU), dict(XTX)]))
    s = {"render": {"processor": False, "card": "1002:0002:0"}}
    assert gpus.window_for(s) == ["--use-adapter-luid=0,95712"]                     # the card chosen, not the biggest
    s["render"]["processor"] = True
    assert gpus.window_for(s) == gpus.CPU_ARGS


def test_a_card_with_no_screen_composes_the_window_on_the_processor(monkeypatch):
    # composed on a card no screen is on, the window is shown through the screen's card, which is then taken too
    monkeypatch.delenv("PAPERDAEMON_WEBGPU_D3D11", raising=False)
    xtx, igpu = dict(XTX, display=True), dict(IGPU, display=False)
    cs = gpus.named([xtx, igpu])
    assert gpus.window_args(cs, igpu["id"]) == ["--use-adapter-luid=0,95712"] + gpus.OFF_SCREEN_ARGS
    assert gpus.window_args(cs, xtx["id"]) == ["--use-adapter-luid=0,82318"]
    assert gpus.window_args(gpus.named([dict(IGPU, display=False)])) == []   # the only card: nothing else to keep off
