# Style Auto Plugin - Tests für style_config.py
#
# Diese Tests prüfen ausschließlich die Parsing-/Coercion-Logik der Konfiguration
# und benötigen kein qgis.core. Sie laufen daher auch mit einem normalen
# Python-Interpreter (z.B. `python -m pytest tests/test_style_config.py`),
# sofern pytest installiert ist.
import json
import os
import sys

import pytest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import style_config as sc  # noqa: E402


# ----------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (True, True),
    (False, False),
    (None, False),
    ("true", True),
    ("True", True),
    ("YES", True),
    ("ja", True),
    ("on", True),
    ("1", True),
    ("0", False),
    ("false", False),
    ("nein", False),
    (1, True),
    (0, False),
])
def test_as_bool_coercion(raw, expected):
    assert sc._as_bool(raw) is expected


def test_as_bool_default_used_for_none():
    assert sc._as_bool(None, default=True) is True
    assert sc._as_bool(None, default=False) is False


def test_as_int_valid_and_invalid():
    assert sc._as_int("5") == 5
    assert sc._as_int(5.9) == 5
    assert sc._as_int("not-a-number", default=42) == 42
    assert sc._as_int(None, default=7) == 7


def test_as_float_valid_and_invalid():
    assert sc._as_float("1.5") == 1.5
    assert sc._as_float("nope", default=0.6) == 0.6


def test_as_list_wraps_scalars_and_passes_lists():
    assert sc._as_list(None) == []
    assert sc._as_list("x") == ["x"]
    assert sc._as_list(["a", "b"]) == ["a", "b"]


def test_get_first_returns_first_matching_key():
    data = {"b": 2, "c": 3}
    assert sc._get_first(data, "a", "b", "c") == 2
    assert sc._get_first(data, "a", default="fallback") == "fallback"


# ----------------------------------------------------------------------
# Dataclass parsers
# ----------------------------------------------------------------------

def test_parse_line_style_def_defaults_and_overrides():
    default_style = sc._parse_line_style_def({})
    assert default_style.color == "#808080"
    assert default_style.width == 0.6
    assert default_style.penstyle == "solid"

    custom_style = sc._parse_line_style_def({"color": "#ff0000", "width": "1.2", "penstyle": "dash"})
    assert custom_style.color == "#ff0000"
    assert custom_style.width == 1.2
    assert custom_style.penstyle == "dash"

    # Kein dict -> Default-Objekt statt Exception
    assert sc._parse_line_style_def(None) == sc.LineStyleDef()


def test_parse_value_rule():
    rule = sc._parse_value_rule({
        "enabled": "false",
        "value": "motorway",
        "label": "Autobahn",
        "style": {"color": "#111111"},
    })
    assert rule.enabled is False
    assert rule.value == "motorway"
    assert rule.label == "Autobahn"
    assert rule.style.color == "#111111"


def test_parse_field_ruleset_legacy_keys_and_fallback():
    data = {
        "enabled": True,
        "fieldname": "highway",  # legacy Schlüssel statt field_name
        "priority": "5",
        "rules": [{"value": "primary", "label": "Primär"}, "not-a-dict"],
        "fallback_style": {"color": "#abcdef"},  # legacy Schlüssel statt fallbackstyle
    }
    ruleset = sc._parse_field_ruleset(data)
    assert ruleset.field_name == "highway"
    assert ruleset.priority == 5
    assert len(ruleset.rules) == 1  # Nicht-Dict-Eintrag wird verworfen
    assert ruleset.fallbackstyle.color == "#abcdef"


def test_parse_match_config_legacy_name_hint_fallback():
    data = {"layer_name_pattern": "roads_*"}
    match = sc._parse_match_config(data)
    assert match.layer_name_pattern == "roads_*"
    # Ohne explizite name_hints wird das Legacy-Pattern als schwacher Hinweis übernommen
    assert match.name_hints == ["roads_*"]


def test_parse_match_config_geometry_type_lowercased():
    match = sc._parse_match_config({"geometrytype": "  LINE  "})
    assert match.geometry_type == "line"


def test_parse_layer_ruleset_legacy_top_level_match_keys():
    data = {
        "layer_name_pattern": "buildings",
        "geometry_type": "polygon",
        "fieldrulesets": [{"field_name": "type"}],
    }
    ruleset = sc._parse_layer_ruleset(data)
    assert ruleset.match.layer_name_pattern == "buildings"
    assert ruleset.match.geometry_type == "polygon"
    assert len(ruleset.fieldrulesets) == 1


def test_parse_plugin_config_legacy_and_default_keys():
    data = {
        "use_fallback_style_for_unknown_values": False,
        "allow_name_mismatch_fallback": "no",
        "compact_legend": "false",
        "styleProfiles": [{"id": "p1"}],
        "layer_rulesets": [{"fieldrulesets": []}],
    }
    config = sc._parse_plugin_config(data)
    assert config.usefallbackstyleforunknownvalues is False
    assert config.allownamemismatchfallback is False
    assert config.compactlegend is False
    assert len(config.style_profiles) == 1
    assert config.style_profiles[0].id == "p1"
    assert len(config.layerrulesets) == 1


def test_parse_plugin_config_defaults_on_empty_dict():
    config = sc._parse_plugin_config({})
    assert config.usefallbackstyleforunknownvalues is True
    assert config.allownamemismatchfallback is True
    assert config.compactlegend is True
    assert config.style_profiles == []
    assert config.layerrulesets == []


def test_parse_plugin_config_non_dict_returns_default():
    config = sc._parse_plugin_config("not-a-dict")
    assert isinstance(config, sc.PluginConfig)


# ----------------------------------------------------------------------
# get_config() - Datei-I/O
# ----------------------------------------------------------------------

def test_get_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_config_path", lambda: str(tmp_path / "does_not_exist.json"))
    config, error = sc.get_config()
    assert config is None
    assert "nicht gefunden" in error


def test_get_config_invalid_json(tmp_path, monkeypatch):
    bad_file = tmp_path / "style_config.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(sc, "_config_path", lambda: str(bad_file))

    config, error = sc.get_config()
    assert config is None
    assert "JSON-Fehler" in error


def test_get_config_valid_file(tmp_path, monkeypatch):
    good_file = tmp_path / "style_config.json"
    good_file.write_text(json.dumps({
        "road_style_mode": 1,
        "enable_landuse_labels": True,
    }), encoding="utf-8")
    monkeypatch.setattr(sc, "_config_path", lambda: str(good_file))

    config, error = sc.get_config()
    assert error is None
    assert isinstance(config, sc.PluginConfig)
