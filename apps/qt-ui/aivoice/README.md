# AI Voice Qt UI

Lightweight emotion-core Qt Quick interface for the RK3568 AI voice terminal.

The application integrates with the ALIENTEK SystemUI through the existing
Qt Remote Objects client under `../client`.

The Python service is connected through `VoiceBridge` using JSON Lines over
`/tmp/ai-voice.sock`. The existing `status/start/stop/cancel` protocol is unchanged.

## Editable components

- `UiTheme.qml`: palette, core size, breathing/float timings and notice duration.
- `VoiceState.js`: six visual states, honest status labels and permitted actions.
- `EmotionCore.qml`: six distinct abstract eye silhouettes, upward thinking gaze,
  listening rings, speaking arcs, four orbiting dots, idle blink and a single-shot
  error contraction. Geometry, gaze and texture changes blend over 280 ms.
- `VoiceWave.qml`: bounded activity indicator. The current protocol has no real
  audio envelope; negative `audioLevel` uses decorative activity, not an audio meter.
- `ConversationCard.qml`: bounded plain-text transcript and answer.
- `DiagnosticsPanel.qml`: long-press the top-left status to open diagnostics.

The centered 720 x 1280 portrait canvas fits both dimensions without cropping.
The top-right Wi-Fi overlay and bottom system gesture region remain reserved.
Animations stop when the app is hidden, backgrounded or covered by diagnostics.
Disconnected service is shown as unavailable, never as working local AI.
Speaking pulses and listening rings are decorative, not real audio-envelope data.

## Validation

```text
[Windows/VM] node tests/test_voice_state.js
```

Production/lifecycle builds still require the existing vendor SDK sibling
`client` and `Repcs` directories. No Buildroot configuration or system component
changes are required. Real screen, frame-rate, RSS and audio-envelope acceptance
must be performed separately on the board.
