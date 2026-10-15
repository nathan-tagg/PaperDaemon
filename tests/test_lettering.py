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
