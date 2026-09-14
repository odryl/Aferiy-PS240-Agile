"""Regression tests for the user-facing off-peak tariff presets."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONST = ROOT / "custom_components" / "aecc_battery" / "const.py"
COORDINATOR = ROOT / "custom_components" / "aecc_battery" / "coordinator.py"
TIME_PLATFORM = ROOT / "custom_components" / "aecc_battery" / "time.py"


def _constants() -> dict[str, object]:
    values: dict[str, object] = {}
    tree = ast.parse(CONST.read_text())
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or value is None:
            continue
        try:
            values[target.id] = eval(
                compile(ast.Expression(value), str(CONST), "eval"),
                {"__builtins__": {}},
                values,
            )
        except (NameError, TypeError):
            continue
    return values


def test_current_uk_tariff_windows() -> None:
    presets = _constants()["TARIFF_PRESETS"]

    assert presets == {
        "octopus_agile": ("23:30", "05:30"),
        "cosy_octopus": ("04:00", "07:00"),
        "snug_octopus": ("00:30", "06:30"),
        "octopus_intelligent_go": ("23:30", "05:30"),
        "octopus_go": ("23:30", "05:30"),
        "edf_goelectric_35": ("23:00", "06:00"),
        "british_gas_electric_driver": ("00:00", "05:00"),
        "eon_next_drive": ("00:00", "06:00"),
        "british_gas_economy_7": ("00:30", "07:30"),
        "edf_e7_fixed": ("00:30", "07:30"),
        "ovo_simpler_energy_e7": ("00:30", "07:30"),
        "octopus_e7": ("00:30", "07:30"),
        "eon_next_pumped_fixed": ("22:00", "06:00"),
        "custom": ("23:30", "05:30"),
    }


def test_tariff_labels_cover_every_preset() -> None:
    constants = _constants()
    presets = constants["TARIFF_PRESETS"]
    labels = constants["TARIFF_PRESET_LABELS"]

    assert labels.keys() == presets.keys()


def test_cosy_octopus_exposes_all_off_peak_and_peak_bands() -> None:
    constants = _constants()

    assert constants["TARIFF_CHEAP_WINDOWS"]["cosy_octopus"] == (
        ("04:00", "07:00"),
        ("13:00", "16:00"),
        ("22:00", "00:00"),
    )
    assert constants["TARIFF_PEAK_WINDOWS"]["cosy_octopus"] == (
        ("16:00", "19:00"),
    )


def test_cosy_dashboard_identifies_cheap_peak_and_day_bands() -> None:
    frontend = (
        ROOT
        / "custom_components"
        / "aecc_battery"
        / "frontend"
        / "aferiy-overnight-plan-card.js"
    ).read_text()

    assert 'attrs.tariff_preset === "cosy_octopus"' in frontend
    assert 'return "Cosy · Cheap"' in frontend
    assert 'return "Cosy · Peak"' in frontend
    assert 'return "Cosy · Day"' in frontend


def test_octopus_agile_is_the_default_tariff() -> None:
    constants = _constants()

    assert constants["DEFAULT_TARIFF_PRESET"] == "octopus_agile"
    assert next(iter(constants["TARIFF_PRESETS"])) == "octopus_agile"


def test_agile_disables_fixed_window_overnight_scheduler() -> None:
    source = COORDINATOR.read_text()

    assert "if preset == OCTOPUS_AGILE_TARIFF_PRESET:" in source
    assert "self.set_overnight_charging_mode(OVERNIGHT_CHARGE_MODE_DISABLED)" in source
    assert "if self.smart_tariff_preset == OCTOPUS_AGILE_TARIFF_PRESET:" in source


def test_manual_off_peak_controls_are_custom_only() -> None:
    source = TIME_PLATFORM.read_text()

    assert 'smart_tariff_preset", None) == "custom"' in source
