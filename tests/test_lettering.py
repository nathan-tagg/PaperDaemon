"""The lettering face has every Latin-1 and Latin Extended-A letter, and accents never move plain text."""
import unicodedata

from paperdaemon.pipeline.draw import lettering as T


def test_every_extended_latin_letter_is_drawn():
    want = [chr(c) for c in range(0xC0, 0x180) if unicodedata.category(chr(c)).startswith("L")]
    assert [ch for ch in want if ch not in T.G] == []
    assert all(T.fold(ch) == ch for ch in "éÅßŁøŒğŵ")          # drawn as themselves, never folded


def test_accents_move_only_the_line_they_are_in():
    assert T.ascent() == T.ascent("plain $ text") == 1.10        # the face's own tallest glyph, `$`
    assert T.ascent("Ångström") > 1.10                           # a capital's mark stands above the cap line
    assert T.descent() == 0.28


def test_fractions_and_signs_are_drawn_as_themselves():
    # "6½–7" was lettered "61/2-7", "¾" came out "34", and "≈" vanished with its meaning
    from paperdaemon.pipeline.draw import symbols as S
    for ch in S.FRACTIONS + S.SUPERSCRIPTS + S.SUBSCRIPTS + "≈±×÷√∞πµ":
        assert ch in T.G and T.fold(ch) == ch, ch
    half = T.G["½"][1]
    top = max(y for p in half for _x, y in p)
    assert top <= 1.0 + 1e-9 and min(y for p in half for _x, y in p) >= -1e-9    # within the cap height
    plain = T.ascent("Bake 6-7 minutes")
    assert T.ascent("Bake 6½–7 minutes ≈ 40 min, x²") >= plain and T.ascent("plain") == T.ascent("plain words")


def test_a_number_and_the_short_word_after_it_stay_on_one_line():
    # DF130: "...November 19 at 3" ended a line and "pm." sat alone at the start of the next
    from paperdaemon.pipeline.draw import lettering as T
    text = "All baked goods must be dropped off in the cafeteria by Thursday, November 19 at 3 pm."
    for width in range(300, 1400, 7):
        for line in T.wrap(text, 30, width):
            assert not line.startswith("pm"), (width, T.wrap(text, 30, width))
    assert T.wrap("one two 3 pm.", 30, T.measure("one two 3", 30, 0.13) + 1) == ["one two", "3 pm."]
