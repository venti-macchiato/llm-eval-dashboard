"""Tests for the optional local Proxima Nova font faces."""

import fonts


def test_empty_directory_emits_nothing(tmp_path):
    assert fonts.font_css(tmp_path) == ""
    assert fonts.font_css(tmp_path / "missing") == ""


def test_rules_are_generated_for_present_files(tmp_path):
    for name in ("ProximaNova-Regular.woff2", "ProximaNova-SemiboldItalic.woff2", "ProximaNova-Bold.woff2"):
        (tmp_path / name).write_bytes(b"fake")
    css = fonts.font_css(tmp_path)
    assert css.count("@font-face") == 3
    assert 'src:url("/static/fonts/ProximaNova-Regular.woff2") format("woff2")' in css
    assert "font-weight:400" in css
    assert "font-weight:600" in css
    assert "font-weight:700" in css
    assert "font-style:italic" in css
    assert "font-display:swap" in css


def test_unknown_name_defaults_to_regular(tmp_path):
    (tmp_path / "CustomFace.woff2").write_bytes(b"fake")
    css = fonts.font_css(tmp_path)
    assert "font-weight:400" in css
    assert "/static/fonts/CustomFace.woff2" in css
