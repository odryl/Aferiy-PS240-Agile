# Dashboard Card

The integration includes a reusable Lovelace card for the smart overnight plan.
It shows target SOC, battery capacity, day balance, Pre-Sunrise Need,
Post-Sunset Need, useful solar, confidence, and SMART History completeness.

## Add The Card Resource

After installing or updating the integration and restarting Home Assistant, add this dashboard resource:

```text
/aecc_battery_static/aferiy-overnight-plan-card.js?v=1.8.22
```

Set the resource type to:

```text
JavaScript module
```

Once the resource is loaded, open a dashboard, choose **Add card**, switch to **By card**, and search for:

```text
AFERIY Overnight Plan
```

## Manual YAML

You can also add it manually:

```yaml
type: custom:aferiy-overnight-plan-card
```

Optional entity overrides are available if your entities have unusual names:

```yaml
type: custom:aferiy-overnight-plan-card
recommended_entity: sensor.aferiy_ps240_local_recommended_overnight_soc
overnight_status_entity: sensor.aferiy_ps240_local_automatic_overnight_charging_status
solar_availability_entity: select.aferiy_ps240_local_solar_availability
smart_history_entity: sensor.aferiy_ps240_local_smart_history
```

The card reads the calculation from the Recommended Overnight SOC sensor. It does not make charging decisions itself.

## Wi-Fi Loss Recovery Card

The separate guarded recovery card is available at:

```text
/aecc_battery_static/aferiy-wifi-recovery-card.js?v=1.8.22
```

After registering it as a JavaScript module, add **AFERIY Wi-Fi Loss Recovery**
from the card picker or use:

```yaml
type: custom:aferiy-wifi-recovery-card
title: Wi-Fi loss recovery
```

The card shows whether the PS240 is available, the current and next Linksys
2.4 GHz channels, consecutive failures, the grace deadline, and the opt-in
switch. Its 0–60 minute grace-period control is persisted by the integration;
valid telemetry before the deadline cancels the channel change. It never
receives or displays router credentials or Wi-Fi passphrases.
