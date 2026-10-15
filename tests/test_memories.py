"""A lineup's memories: the model adds, replaces and removes them; at most MAX; renamed with the lineup."""
import pytest

from paperdaemon import memories


def test_the_model_adds_replaces_and_removes():
    done = memories.apply("L", [{"text": "Erase my request   once done."}, {"text": "Keep answers short."}])
    assert done == ["remembered m1: Erase my request once done.", "remembered m2: Keep answers short."]
    done = memories.apply("L", [{"text": "Keep answers to one line.", "replaces": "m2"}, {"text": "", "replaces": "m1"}])
    assert done == ["replaced m2: Keep answers to one line.", "forgot m1"]
    assert [(m["id"], m["text"]) for m in memories.of("L")] == [("m2", "Keep answers to one line.")]
    assert memories.apply("L", [{"text": "x", "replaces": "m9"}]) == ["not kept (no memory m9)"]


def test_a_full_lineup_must_replace():
    for i in range(memories.MAX):
        memories.add("L", "lesson %d" % i)
    with pytest.raises(ValueError):
        memories.add("L", "one more")
    assert memories.apply("L", [{"text": "one more"}])[0].startswith("not kept (this lineup already keeps 30")
    assert memories.apply("L", [{"text": "one more", "replaces": "m1"}])[0] == "replaced m1: one more"


def test_rename_keeps_and_drop_deletes():
    memories.add("A", "lesson")
    memories.rename("A", "B")
    assert memories.of("A") == [] and memories.of("B")[0]["text"] == "lesson"
    memories.drop("B")
    assert memories.of("B") == []
