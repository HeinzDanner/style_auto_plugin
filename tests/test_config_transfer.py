import copy
import json

import pytest


@pytest.fixture
def dialog(qgis_app):
    from qgis.PyQt import sip
    from style_auto_plugin.style_auto_plugin_dialog import StyleAutoPluginDialog

    widget = StyleAutoPluginDialog(active_config={"custom_mappings": []})
    yield widget
    widget.close()
    sip.delete(widget)


def _mock_file_dialog(monkeypatch, method, path):
    from style_auto_plugin import style_auto_plugin_dialog as module

    monkeypatch.setattr(module.QFileDialog, method, lambda *args: (str(path), "JSON (*.json)"))


def test_configuration_export_import_roundtrip(dialog, monkeypatch, tmp_path):
    original = {
        "road_style_mode": 3,
        "enable_advanced_road_features": False,
        "enable_advanced_building_features": False,
        "enable_advanced_point_features": False,
        "enable_road_labels": False,
        "enable_building_edge_smoothing": True,
        "enable_building_drop_shadow": False,
        "enable_building_labels": False,
        "enable_landuse_labels": True,
        "compactlegend": False,
        "style_profiles": [],
        "layerrulesets": [{"enabled": True, "fieldrulesets": []}],
        "extra_setting": {"preserved": "yes"},
        "custom_mappings": [
            {"active": True, "geom": "Polygon", "value": "apartments",
             "style": "__missing_symbol__", "label": "Wohngebäude"},
            {"active": False, "geom": "Line", "value": "motorway",
             "style": "autobahn", "label": "Autobahn"},
        ],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8-sig")
    target = tmp_path / "export.json"
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.load_configuration()
    assert dialog.config == original
    assert len(dialog.mapping_rows) == 2
    assert dialog.mapping_rows[0]["active"].isChecked()
    assert dialog.mapping_rows[0]["style"].isEnabled()
    assert dialog.mapping_rows[0]["container"].toolTip()
    assert dialog.mode_combo.currentIndex() == 3
    _mock_file_dialog(monkeypatch, "getSaveFileName", target)
    dialog.save_configuration()
    assert json.loads(target.read_text(encoding="utf-8")) == original

    from style_auto_plugin.style_auto_plugin_dialog import StyleAutoPluginDialog
    from qgis.PyQt import sip
    reopened = StyleAutoPluginDialog(active_config=copy.deepcopy(dialog.config))
    try:
        assert reopened.config == original
        assert len(reopened.mapping_rows) == 2
    finally:
        reopened.close()
        sip.delete(reopened)


def test_configuration_load_empty_list_replaces_existing_rows(dialog, monkeypatch, tmp_path):
    dialog.add_mapping_row()
    source = tmp_path / "empty.json"
    source.write_text('{"custom_mappings": [], "road_style_mode": 0}', encoding="utf-8")
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.load_configuration()
    assert not dialog.mapping_rows
    assert dialog.config["custom_mappings"] == []
    assert dialog.mode_combo.currentIndex() == 0


def test_load_updates_visible_dialog_without_reopening(dialog, monkeypatch, tmp_path, qgis_app):
    dialog.add_mapping_row()
    dialog.show()
    qgis_app.processEvents()
    old_container = dialog.mapping_rows[0]["container"]
    assert old_container.isVisible()
    source = tmp_path / "visible.json"
    config = {
        "road_style_mode": 3,
        "enable_road_labels": False,
        "enable_building_drop_shadow": False,
        "custom_mappings": [
            {"active": False, "geom": "Polygon", "value": "forest",
             "style": "forest_symbol", "label": "Loaded forest"},
            {"active": True, "geom": "Line", "value": "primary",
             "style": "road_symbol", "label": "Loaded road"},
        ],
    }
    source.write_text(json.dumps(config), encoding="utf-8")
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.load_configuration()

    assert dialog.isVisible()
    assert not old_container.isVisible()
    assert dialog.mode_combo.currentIndex() == 3
    assert not dialog.cb_road_labels.isChecked()
    assert not dialog.cb_building_shadow.isChecked()
    assert dialog.scroll_layout.count() == 2
    for row, expected in zip(dialog.mapping_rows, config["custom_mappings"]):
        assert row["container"].isVisible()
        assert row["active"].isChecked() == expected["active"]
        assert row["geom"].currentText() == expected["geom"]
        for key in ("value", "style", "label"):
            assert row[key].text() == expected[key]

    source.write_text('{"custom_mappings": [], "road_style_mode": 0}', encoding="utf-8")
    old_rows = [row["container"] for row in dialog.mapping_rows]
    dialog.load_configuration()
    assert all(not container.isVisible() for container in old_rows)
    assert dialog.scroll_layout.count() == 0
    assert dialog.mode_combo.currentIndex() == 0
    assert dialog.cb_road_labels.isChecked()


@pytest.mark.parametrize("content", [
    "{invalid", "[]", '{"road_style_mode": 9}',
    '{"enable_road_labels": "false"}', '{"custom_mappings": {}}',
    '{"custom_mappings": [{"geom":"Polygon", "active":"false"}]}',
    '{"style_profiles": "invalid"}',
])
def test_configuration_invalid_load_does_not_change_state(dialog, monkeypatch, tmp_path, content):
    from style_auto_plugin import style_auto_plugin_dialog as module

    before = copy.deepcopy(dialog.config)
    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warnings.append(args))
    source = tmp_path / "invalid.json"
    source.write_text(content, encoding="utf-8")
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.load_configuration()
    assert warnings
    assert dialog.config == before
    assert not dialog.mapping_rows


def test_configuration_cancel_does_nothing(dialog, monkeypatch):
    before = copy.deepcopy(dialog.config)
    _mock_file_dialog(monkeypatch, "getOpenFileName", "")
    _mock_file_dialog(monkeypatch, "getSaveFileName", "")
    dialog.load_configuration()
    dialog.save_configuration()
    assert dialog.config == before


def test_configuration_export_reports_write_failure(dialog, monkeypatch, tmp_path):
    from style_auto_plugin import style_auto_plugin_dialog as module

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warnings.append(args))
    _mock_file_dialog(monkeypatch, "getSaveFileName", tmp_path / "missing" / "export.json")
    dialog.save_configuration()
    assert warnings


def test_loaded_configuration_edits_are_exported_without_reopening(dialog, monkeypatch, tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "road_style_mode": 1,
        "custom_mappings": [
            {"active": False, "geom": "Polygon", "value": "forest",
             "style": "forest_symbol", "label": "Old label"},
        ],
    }), encoding="utf-8")
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.load_configuration()
    row = dialog.mapping_rows[0]
    row["active"].setChecked(True)
    row["geom"].setCurrentText("Line")
    row["value"].setText("primary")
    row["style"].setText("my_road")
    row["label"].setText("Edited road")
    dialog.mode_combo.setCurrentIndex(3)
    dialog.cb_road_labels.setChecked(False)

    target = tmp_path / "edited.json"
    _mock_file_dialog(monkeypatch, "getSaveFileName", target)
    dialog.btn_save.click()
    exported = json.loads(target.read_text(encoding="utf-8"))
    assert exported["road_style_mode"] == 3
    assert exported["enable_road_labels"] is False
    assert exported["custom_mappings"] == [{
        "active": True, "geom": "Line", "value": "primary",
        "style": "my_road", "label": "Edited road",
    }]


def test_failed_import_preserves_populated_dialog_and_export(dialog, monkeypatch, tmp_path):
    from style_auto_plugin import style_auto_plugin_dialog as module

    dialog.add_mapping_row()
    row = dialog.mapping_rows[0]
    row["value"].setText("forest")
    row["style"].setText("my_forest")
    row["label"].setText("Keep this")
    dialog.mode_combo.setCurrentIndex(3)
    before = copy.deepcopy(dialog.config)
    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warnings.append(args))
    source = tmp_path / "broken.json"
    source.write_text('{"custom_mappings": [{"geom": "invalid"}]}', encoding="utf-8")
    _mock_file_dialog(monkeypatch, "getOpenFileName", source)
    dialog.btn_load.click()
    assert warnings
    assert dialog.config == before
    assert dialog.mapping_rows[0] is row
    assert row["label"].text() == "Keep this"
    target = tmp_path / "unchanged.json"
    _mock_file_dialog(monkeypatch, "getSaveFileName", target)
    dialog.save_configuration()
    assert json.loads(target.read_text(encoding="utf-8")) == before
