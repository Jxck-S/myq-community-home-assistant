# myQ Community Home Assistant Integration
<img src="assets/logo.png" width="200" />

This integration lets you open your **myQ Community** gates and doors from Home Assistant and see the latest access event.

> [!NOTE]
> This is for **myQ Community**, Chamberlain's access-control platform for apartment communities and managed buildings: the app residents use for community gates, lobby doors and access panels. It is **not** for consumer myQ garage door openers.

> [!WARNING]
> **For educational and personal use only.** This integration is an unofficial, independent project. It is not affiliated with, endorsed by, or supported by Chamberlain Group / myQ. It works by using the same private API as the official mobile app, which can change or stop working at any time without notice.
>
> - Use it only with your own account and only for doors you are authorized to access.
> - You are responsible for complying with myQ's Terms of Service and your community's policies.
> - This software is provided "as is", without warranty of any kind. The authors are not liable for any damages, account suspensions, or security issues resulting from its use.

## Installation

Requires Home Assistant 2026.3 or newer.

### HACS (recommended)
1. In HACS, open the menu (⋮) > **Custom repositories**.
2. Add `https://github.com/Jxck-S/myq-community-home-assistant` with category **Integration**.
3. Search for **myQ Community** in HACS and download it.
4. Restart Home Assistant.

### Manual
1. Copy `custom_components/myq_community` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

Home Assistant installs the [myq-community-client](https://github.com/Jxck-S/myq-community-client) library automatically.

### Setup
1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for "myQ Community".
3. Enter the email and password you use in the myQ Community app.
4. myQ texts or emails you a one-time code. Enter it on the next screen. (Accounts without two-factor authentication skip this step.)

Home Assistant stores only a login token, **not your password**. It renews the token automatically, so you won't be asked for a code again unless the token stops working (for example, after you sign out everywhere or the account is locked). In that case Home Assistant shows a **Reauthenticate** prompt that asks for your password and a new code.

## Entities

Each community on your account shows up as a device with these entities:

*   **Locks**: One per gate, door or lock you can unlock.
    *   **Gates and access-panel doors**: **Unlock** opens them. They show as unlocked for 10 seconds, then locked again, because they re-lock themselves. Repeat unlocks within 20 seconds are ignored. A device that myQ reports as offline shows as unavailable.
    *   **Smart locks** (`remote_lock`): **Lock** and **Unlock** send the matching command. myQ doesn't report lock state, so the entity shows the last command sent. Smart locks haven't been tested on real hardware yet; please report how they behave.
*   **Sensors**:
    *   **Last Access**: The device and event of the most recent access, for example "Gate - unlocked". Attributes include the device, serial number and timestamp.
    *   **Last Access Time**: When the latest access actually happened, according to myQ. Shown as "5 minutes ago" and usable in automations.

Data is refreshed every 5 minutes, with one devices request and one history request per community. Opening a gate from Home Assistant triggers an extra refresh so the sensors pick up the new event.

## Troubleshooting

*   **Asked to reauthenticate?** Enter your password and the new code under **Settings > Devices & Services**.
*   **myQ unreachable?** Entities show as unavailable and Home Assistant keeps retrying. Outages don't trigger reauthentication.
*   **Debug logs:** add this to `configuration.yaml`:
    ```yaml
    logger:
      logs:
        custom_components.myq_community: debug
        myqcommunity: debug
    ```

## Tested devices

Tested live with an `access_panel` gate (`device_type: access_panel_door`). Other device types are implemented from the known API shape but haven't been exercised on real hardware. If something doesn't work for your setup, please open an issue with your device's `device_family` / `device_type`.

## Development

Tests run inside a real Home Assistant test instance with the myQ Community client mocked:

```bash
pip install -r requirements_test.txt
ruff check .
pytest
```

## License

[MIT](LICENSE). See the disclaimer at the top: this is an unofficial project, not affiliated with Chamberlain Group / myQ.
