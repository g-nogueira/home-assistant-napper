# Home Assistant Napper

Unofficial, read-only Home Assistant integration for
[Napper](https://napper.app/).

> [!WARNING]
> This project uses a private, undocumented Napper API. It is not affiliated
> with or endorsed by Napper, and an app update can break the integration.

## What it provides

The integration creates one Home Assistant device for each baby in the Napper
account. Each device exposes:

| Entity | Meaning |
| --- | --- |
| `binary_sensor.*_sleeping` | The baby is in a nap or night sleep |
| `binary_sensor.*_napping` | An unpaused daytime nap is open |
| `binary_sensor.*_nap_paused` | A daytime nap tracker is open and paused |
| `binary_sensor.*_nursing` | A nursing tracker is open |
| `binary_sensor.*_night_waking` | A night waking tracker is open |
| `sensor.*_sleep_state` | `awake`, `napping`, `nap_paused`, `night_sleeping`, or `night_waking` |
| `sensor.*_sleep_started_at` | Start of the current sleep session |
| `sensor.*_last_activity_at` | Latest log or pause timestamp seen |

Activity flags are independent. Napper can, for example, report nursing while
a nap remains open.

## Install

### HACS custom repository

1. Open HACS in Home Assistant.
2. Add `https://github.com/g-nogueira/home-assistant-napper` as a custom
   repository with type **Integration**.
3. Install **Napper**.
4. Restart Home Assistant.

### Manual

Copy `custom_components/napper` into the `custom_components` directory in your
Home Assistant configuration, then restart Home Assistant.

## Configure

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Napper**.
3. Enter the email address used in Napper.
4. Enter the one-time code sent by Napper.

To change the polling interval afterwards, open **Settings → Devices &
services → Napper → Configure**. The default is 60 seconds; values from 30 to
3600 seconds are supported. The integration reloads after saving the option.

The integration stores the resulting ID and refresh tokens in the Home
Assistant config entry, as other authenticated integrations do. It refreshes
the ID token before expiration and asks for reauthentication if Napper rejects
the stored credentials.

## Behavior and privacy

- The integration is strictly read-only. It does not create, edit, or delete
  Napper logs.
- It polls once every 60 seconds.
- It does not log email addresses, tokens, baby IDs, baby names, or API bodies.
- Do not attach mitmproxy flows, HAR files, or Home Assistant storage files to
  issues; they can contain long-lived credentials and family data.

## Known limitations

- The API is private and has no compatibility guarantee.
- Rate limits and external-client terms are not documented.
- Babies added to the account after setup appear after reloading the
  integration.
- Night sleep is inferred from the latest `BED_TIME` or `WOKE_UP` marker and an
  open `NIGHT_WAKING` log. This matches the observed app behavior but is not an
  official Napper contract.

## Development

The API and state-derivation tests use only sanitized synthetic fixtures.

```bash
python -m pip install -r requirements_test.txt
ruff check .
pytest
```

## License

[MIT](LICENSE)
