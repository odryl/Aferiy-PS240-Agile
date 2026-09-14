"""Constants for the AFERIY PS240 local integration."""

DOMAIN = "aecc_battery"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_EXTENDED_POWER = "extended_power"
CONF_ADVANCED_ENERGY_SENSORS = "advanced_energy_sensors"
CONF_POLL_INTERVAL = "poll_interval"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_TARIFF_PRESET = "tariff_preset"
CONF_OFF_PEAK_START = "off_peak_start"
CONF_OFF_PEAK_END = "off_peak_end"
CONF_OVERNIGHT_CHARGING_MODE = "overnight_charging_mode"
CONF_DEPENDENCY_SOLCAST = "dependency_solcast_confirmed"
CONF_DEPENDENCY_HOME_OCCUPANCY = "dependency_home_occupancy_confirmed"
CONF_AGILE_PLANNER_ENABLED = "agile_planner_enabled"
CONF_AGILE_CURRENT_DAY_RATES_ENTITY = "agile_current_day_rates_entity"
CONF_AGILE_NEXT_DAY_RATES_ENTITY = "agile_next_day_rates_entity"
CONF_AGILE_READY_BY = "agile_ready_by"
CONF_AGILE_PROTECTED_UNTIL = "agile_protected_until"
CONF_WIFI_LOSS_RECOVERY_ROUTER_HOST = "wifi_loss_recovery_router_host"
CONF_WIFI_LOSS_RECOVERY_ROUTER_PASSWORD = "wifi_loss_recovery_router_password"

# Default connection values
DEFAULT_HOST = "192.168.0.1"
DEFAULT_PORT = 8080
DEFAULT_NAME = "AFERIY PS240 (Local)"
DEFAULT_MANUFACTURER = "AFERIY"
DEFAULT_MODEL = "PS240"
DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_OFF_PEAK_START = "23:30"
DEFAULT_OFF_PEAK_END = "05:30"
OCTOPUS_AGILE_TARIFF_PRESET = "octopus_agile"
COSY_OCTOPUS_TARIFF_PRESET = "cosy_octopus"
DEFAULT_TARIFF_PRESET = OCTOPUS_AGILE_TARIFF_PRESET
OVERNIGHT_CHARGE_MODE_DISABLED = "disabled"
OVERNIGHT_CHARGE_MODE_SMART = "smart"
OVERNIGHT_CHARGE_MODE_MANUAL = "manual"
DEFAULT_OVERNIGHT_CHARGE_MODE = OVERNIGHT_CHARGE_MODE_DISABLED
DEFAULT_AGILE_PLANNER_ENABLED = True
DEFAULT_AGILE_READY_BY = "16:00"
DEFAULT_AGILE_PROTECTED_UNTIL = "22:00"
DEFAULT_WIFI_LOSS_RECOVERY_ROUTER_HOST = "192.168.0.1"
WIFI_LOSS_RECOVERY_CHANNELS = (6, 11)
WIFI_LOSS_RECOVERY_COOLDOWN_HOURS = 1
WIFI_LOSS_RECOVERY_DEFAULT_GRACE_MINUTES = 0
WIFI_LOSS_RECOVERY_MAX_GRACE_MINUTES = 60
WIFI_LOSS_RECOVERY_VERIFY_SECONDS = 45

# Confirmed system-level limits used by Agile planning. AC grid charging and
# CT-controlled household supply have different ceilings; neither value changes
# the experimental per-register controls exposed elsewhere in the integration.
AGILE_MAX_SYSTEM_CHARGE_POWER_W = 1200
AGILE_MAX_SYSTEM_DISCHARGE_POWER_W = 1000
AGILE_DEMAND_PROFILE_REVISION = "shadow_2026_08_net_median_v3"

# Anonymized half-hour net-demand medians from 12 complete schema-v2 shadow
# days.  Each value is household demand after measured PV, so the advisory
# plan no longer assumes that daytime solar can also be displaced by battery
# discharge.  Live CT feedback remains the zero-export safety control.
AGILE_DEFAULT_DEMAND_PROFILE_KWH: dict[str, float] = {
    "16:00": 0.123,
    "16:30": 0.136,
    "17:00": 0.132,
    "17:30": 0.162,
    "18:00": 0.165,
    "18:30": 0.181,
    "19:00": 0.253,
    "19:30": 0.210,
    "20:00": 0.202,
    "20:30": 0.195,
    "21:00": 0.189,
    "21:30": 0.345,
}
OVERNIGHT_CHARGE_MODE_LABELS: dict[str, str] = {
    OVERNIGHT_CHARGE_MODE_SMART: "On",
    OVERNIGHT_CHARGE_MODE_DISABLED: "Off",
    OVERNIGHT_CHARGE_MODE_MANUAL: "Manual",
}
OVERNIGHT_CHARGE_MODE_FROM_LABEL: dict[str, str] = {
    label: value for value, label in OVERNIGHT_CHARGE_MODE_LABELS.items()
}
OVERNIGHT_CHARGE_MODE_FROM_LABEL["Disabled"] = OVERNIGHT_CHARGE_MODE_DISABLED
TARIFF_PRESETS: dict[str, tuple[str, str]] = {
    # Agile is dynamic: this compatibility window is never used by the fixed-
    # window overnight scheduler, which is interlocked while Agile is selected.
    OCTOPUS_AGILE_TARIFF_PRESET: (DEFAULT_OFF_PEAK_START, DEFAULT_OFF_PEAK_END),
    # The morning dip is the primary window used by the overnight battery
    # target. All three Cosy dips are exposed separately below for dashboards.
    COSY_OCTOPUS_TARIFF_PRESET: ("04:00", "07:00"),
    "snug_octopus": ("00:30", "06:30"),
    "octopus_intelligent_go": (DEFAULT_OFF_PEAK_START, DEFAULT_OFF_PEAK_END),
    "octopus_go": ("23:30", "05:30"),
    "edf_goelectric_35": ("23:00", "06:00"),
    "british_gas_electric_driver": ("00:00", "05:00"),
    "eon_next_drive": ("00:00", "06:00"),
    "british_gas_economy_7": ("00:30", "07:30"),
    "edf_e7_fixed": ("00:30", "07:30"),
    "ovo_simpler_energy_e7": ("00:30", "07:30"),
    "octopus_e7": ("00:30", "07:30"),
    "eon_next_pumped_fixed": ("22:00", "06:00"),
    "custom": (DEFAULT_OFF_PEAK_START, DEFAULT_OFF_PEAK_END),
}
TARIFF_PRESET_LABELS: dict[str, str] = {
    OCTOPUS_AGILE_TARIFF_PRESET: "Octopus Agile (dynamic rates; Proposed Plan)",
    COSY_OCTOPUS_TARIFF_PRESET: (
        "Cosy Octopus (04:00-07:00, 13:00-16:00, 22:00-00:00)"
    ),
    "snug_octopus": "Snug Octopus (00:30-06:30)",
    "octopus_intelligent_go": "Intelligent Octopus Go (23:30-05:30)",
    "octopus_go": "Octopus Go (23:30-05:30)",
    "edf_goelectric_35": "EDF GoElectric 35 (23:00-06:00)",
    "british_gas_electric_driver": "British Gas EV Power+ (00:00-05:00)",
    "eon_next_drive": "E.ON Next Drive (00:00-06:00)",
    "british_gas_economy_7": "British Gas Standard E7 (00:30-07:30)",
    "edf_e7_fixed": "EDF E7 Fixed (00:30-07:30)",
    "ovo_simpler_energy_e7": "OVO Simpler Energy E7 (00:30-07:30)",
    "octopus_e7": "Octopus E7 (00:30-07:30)",
    "eon_next_pumped_fixed": "E.ON Next Pumped Fixed (22:00-06:00)",
    "custom": "Custom/manual times",
}

# Fixed local-clock rate bands used for display and tariff-aware behaviour.
# Cosy unit prices vary by region and product version, so the integration does
# not hard-code p/kWh values. The primary morning dip in TARIFF_PRESETS remains
# the sole window used by the existing overnight charge-to-target algorithm.
TARIFF_CHEAP_WINDOWS: dict[str, tuple[tuple[str, str], ...]] = {
    COSY_OCTOPUS_TARIFF_PRESET: (
        ("04:00", "07:00"),
        ("13:00", "16:00"),
        ("22:00", "00:00"),
    ),
}
TARIFF_PEAK_WINDOWS: dict[str, tuple[tuple[str, str], ...]] = {
    COSY_OCTOPUS_TARIFF_PRESET: (("16:00", "19:00"),),
}

# Polling
POLL_INTERVAL = 5  # seconds – change this to update faster/slower
MIN_POLL_INTERVAL = 2  # seconds – hard floor to avoid flooding the device

# Power limits
MIN_CHARGE_POWER_W = 200  # watts per unit – lowest exposed local charge target
DEFAULT_CHARGE_POWER_W = 800  # watts per unit – default for new installations
MAX_REGISTER_POWER_DEFAULT = 800  # watts – observed reliable local TCP lower/default limit
PS240_EXPERIMENTAL_MAX_OUTPUT_W = 1200  # watts per unit – exposed for cautious local testing

# Backwards-compatible name used by coordinator.py
MAX_BATTERY_POWER_W = PS240_EXPERIMENTAL_MAX_OUTPUT_W

# Battery capacity presets
BATTERY_MODULE_CAPACITY_KWH = 1.958
DEFAULT_BATTERY_MODULE_COUNT = 3
DEFAULT_BATTERY_CAPACITY_KWH = round(
    BATTERY_MODULE_CAPACITY_KWH * DEFAULT_BATTERY_MODULE_COUNT,
    3,
)
BATTERY_CAPACITY_PRESET_MODULE_COUNTS = tuple(range(1, 16))


def battery_capacity_for_modules(module_count: int) -> float:
    """Return total capacity for an AFERIY stack module count."""
    return round(float(module_count) * BATTERY_MODULE_CAPACITY_KWH, 3)


def battery_capacity_preset_label(module_count: int) -> str:
    """Human-readable capacity preset label."""
    capacity = battery_capacity_for_modules(module_count)
    suffix = "module" if module_count == 1 else "modules"
    return f"{module_count} {suffix} ({capacity:.2f} kWh)"


# ─── Sensor cleaning profile ─────────────────────────────────────────────────
# Per-brand thresholds for the physics-aware SOC cleaner.
# - soc_zero_reject_during_active_w: reject SOC=0 readings when the absolute
#   wall-side power exceeds this threshold.
# - soc_max_rate_pct_per_min: discard SOC readings whose change rate from the
#   last accepted sample exceeds this.
# - hold_last_value_seconds: how long an entity may keep returning its last
#   accepted value after readings start being rejected before going unavailable.
# ──────────────────────────────────────────────────────────────────────────────

CONF_BRAND_PROFILE_KEY = "brand_profile"

BRAND_PROFILES: dict[str, dict[str, float | int]] = {
    "AFERIY": {
        "soc_zero_reject_during_active_w": 100,
        "soc_max_rate_pct_per_min": 8.0,
        "hold_last_value_seconds": 120,
    },
    "Lunergy": {
        "soc_zero_reject_during_active_w": 50,
        "soc_max_rate_pct_per_min": 5.0,
        "hold_last_value_seconds": 120,
    },
    "Sunpura": {
        "soc_zero_reject_during_active_w": 200,
        "soc_max_rate_pct_per_min": 10.0,
        "hold_last_value_seconds": 120,
    },
    "Voltdeer": {
        "soc_zero_reject_during_active_w": 200,
        "soc_max_rate_pct_per_min": 10.0,
        "hold_last_value_seconds": 120,
    },
    "AEG": {
        "soc_zero_reject_during_active_w": 200,
        "soc_max_rate_pct_per_min": 10.0,
        "hold_last_value_seconds": 120,
    },
    "Other": {
        "soc_zero_reject_during_active_w": 100,
        "soc_max_rate_pct_per_min": 8.0,
        "hold_last_value_seconds": 120,
    },
}

DEFAULT_BRAND_PROFILE: dict[str, float | int] = BRAND_PROFILES["AFERIY"]


# ─── Control register addresses ───────────────────────────────────────────────
REG_EMS_ENABLE = "3000"  # 0 = off, 1 = on
REG_SCHEDULE_MODE = "3020"  # Schedule mode; 6 = custom schedule
REG_AI_SMART_CHARGE = "3021"  # 0 = off, 1 = on
REG_AI_SMART_DISC = "3022"  # 0 = off, 1 = on
REG_CUSTOM_MODE = "3030"  # 0 = off, 1 = on

# Power setpoint, time-slot format:
#   "timeSwitch,startHH:MM,endHH:MM,powerW,0,mode,0,0,0,chargingSOC,dischargingSOC"
#   e.g. "1,00:00,23:59,800,0,6,0,0,0,100,10"     (discharge at 800 W)
#        "1,00:00,23:59,-800,0,6,0,0,0,100,10"    (charge at 800 W)
#        "0,00:00,00:00,0,0,0,0,0,0,100,10"       (idle / disabled)
REG_CONTROL_TIME1 = "3003"  # First active time slot
REG_CONTROL_TIME2 = "3004"  # Second active time slot

REG_MIN_SOC = "3023"  # Minimum discharge SOC
REG_MAX_SOC = "3024"  # Maximum charge SOC
REG_BASE_DISCHARGE_POWER = "3026"  # Base grid-connected feed/discharge power (W)
REG_BASE_DISCHARGE_ENABLE = "3029"  # Enables base grid-connected feed/discharge behavior
REG_SURPLUS_CHARGE_TRIGGER = "3037"  # PV surplus trigger for grid-connected charging (W)
REG_MAX_FEED_POWER = "3039"  # Max feed power in W; read/write depends on integration logic

# Empty schedule slot - clears the active time slot.
SLOT_DISABLED = "0,00:00,00:00,0,0,0,0,0,0,100,10"


# ─── Work modes ───────────────────────────────────────────────────────────────
MODE_SELF_CONSUMPTION = "Self-Consumption (AI)"
MODE_CUSTOM = "Custom / Manual"
MODE_DISABLED = "Disabled"

# Register sets for each mode.
#
# Note:
# The main coordinator may override Self-Consumption with its own robust
# async_restore_self_consumption() method. This dictionary is still kept for
# compatibility with the original integration structure.
MODE_REGISTERS = {
    MODE_SELF_CONSUMPTION: {
        REG_EMS_ENABLE: "1",
        REG_AI_SMART_CHARGE: "1",
        REG_AI_SMART_DISC: "1",
        REG_CUSTOM_MODE: "0",
        REG_CONTROL_TIME1: SLOT_DISABLED,
    },
    MODE_CUSTOM: {
        REG_EMS_ENABLE: "1",
        REG_AI_SMART_CHARGE: "0",
        REG_AI_SMART_DISC: "0",
        REG_CUSTOM_MODE: "1",
    },
    MODE_DISABLED: {
        REG_EMS_ENABLE: "0",
    },
}
