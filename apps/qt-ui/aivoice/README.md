# AI Voice Qt UI

Minimal black-and-white Qt Quick interface for the RK3568 AI voice terminal.

The application integrates with the ALIENTEK SystemUI through the existing
Qt Remote Objects client under `../client`.

Current scope:

- SystemUI application lifecycle integration
- Idle and recording visual states
- Signals reserved for recording start and stop
- Transcript and answer presentation areas

The Python voice service transport is intentionally not included in this
first UI-only version.
