# Local wake greeting

`wake-hello.wav` is the fixed phrase "你好", generated once using the existing
MiMo TTS configuration. It contains no credentials or user recording.
Format: mono PCM16, 16 kHz, at most 1.5 seconds. No TTS request occurs at wake time.
Current asset is 0.68 seconds: the original first 0.56 seconds is unchanged;
an 80 ms post-voice margin, 20 ms quiet-tail fade and 40 ms zero drain tail
replace the original low-level trailing residue. Original 0.96-second audio is
kept in the local/board deployment backups. Actual perceived tail quality still
requires the user's listening check.
The service validates this asset before local bounded playback; if missing or
invalid, it uses a local tone rather than waiting for a network request.
Deploy alongside `voice_service.py`. Keep generated voice use within the existing
self-use/demo scope; verify provider terms before public redistribution.
