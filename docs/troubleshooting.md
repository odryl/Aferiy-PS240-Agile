# Troubleshooting

## Device Cannot Connect

- Confirm the battery has a stable local IP address.
- Confirm TCP port `8080` is reachable from Home Assistant.
- Reserve the battery IP in your router so it does not change.
- Restart Home Assistant after installing or updating the integration.

## Entities Are Unavailable

Check the `Connection Status` and `Consecutive Poll Failures` entities first. These show whether the local TCP poll is succeeding or whether Home Assistant is using the last good data.

## Wi-Fi Loss Recovery Does Not Enable

- Configure the Linksys router address and **local router administrator**
  password in the AFERIY integration options. The Linksys cloud-account password
  is not used.
- Confirm Home Assistant can reach the router locally over HTTPS.
- The router must identify itself as Linksys and advertise the JNAP WirelessAP4
  service. The validated installation uses the toob Linksys SPNMX56TB/Velop.
- Keep the 2.4 GHz radio manually set to channel 6 or 11. Other starting channels
  are deliberately rejected.
- Set `Wi-Fi Recovery Grace Period` to 0 for an immediate change, or up to 60
  minutes to allow self-recovery or a manual intervention first. A successful
  battery poll during the wait cancels the pending change.
- A one-hour cooldown prevents another change even if Home Assistant restarts.
  Check the switch's `next_allowed_attempt_at` attribute.
- Prefer Ethernet for the Home Assistant host. A host connected through the same
  2.4 GHz radio may briefly lose access while the channel changes.

## Commands Do Not Appear To Apply

Check `Last Command Result`. The integration records whether the battery acknowledged the command and whether the follow-up register read matched the requested value.

If a command is acknowledged but not verified, the battery may have ignored or normalised part of the register write. Download diagnostics and include them in a GitHub issue.

## Advanced Estimate Sensors Are Missing

The advanced estimate sensors are optional. Open the integration options and enable `Advanced energy estimate sensors`.
