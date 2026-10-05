"""Offline wire-format, audio and recovery tests. Never call a real endpoint."""
import base64
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from asr.mimo_asr import MiMoASR
from audio.pcm import AudioFormatError, PCM16Resampler, normalize_wav, read_wav
from audio.play import AudioPlayer
from config.settings import read_local_values
from llm.mimo import MiMoLLM
from mimo_http import MiMoError, MiMoHTTP
from tts.mimo_tts import MiMoTTS


def wav_bytes(rate=24000, channels=1, width=2, frames=600):
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setparams((channels, width, rate, 0, "NONE", "not compressed"))
        handle.writeframes(b"\x20\x01" * (frames * channels * width // 2))
    return output.getvalue()


def audio_result(data=None):
    return {"choices": [{"finish_reason": "stop", "message": {
        "audio": {"data": base64.b64encode(wav_bytes() if data is None else data).decode()}}}]}


def audio_event(data):
    return {"choices": [{"delta": {"audio": {"data": base64.b64encode(data).decode()}},
                         "finish_reason": None}]}


def sse(*events, done=True):
    body = b": heartbeat\r\n\r\n"
    for event in events:
        body += b"data:" + json.dumps(event, ensure_ascii=False).encode() + b"\r\n\r\n"
    return body + (b"data: [DONE]\n\n" if done else b"")


class Response:
    def __init__(self, data, status=200, streaming=False, failure=None):
        self.status_code = status
        self.headers = {"Content-Type": "text/event-stream" if streaming else "application/json"}
        self.body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.closed = False
        self.failure = failure

    def iter_content(self, chunk_size=1):
        for pos in range(0, len(self.body), chunk_size):
            yield self.body[pos:pos + chunk_size]
        if self.failure:
            raise self.failure

    def close(self):
        self.closed = True


def transport(*responses):
    session = mock.Mock()
    session.post.side_effect = responses
    return MiMoHTTP(api_key="offline-placeholder", session=session), session


class MiMoASRTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.wav"
        self.path.write_bytes(wav_bytes(16000))

    def test_success_uses_audio_message_and_original_wav(self):
        response = Response({"choices": [{"message": {"content": " 你好。 "}, "finish_reason": "stop"}]})
        http, session = transport(response)
        self.assertEqual(MiMoASR(http=http).recognize(self.path), "你好。")
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "mimo-v2.5-asr")
        encoded = payload["messages"][0]["content"][0]["input_audio"]["data"]
        self.assertEqual(base64.b64decode(encoded.split(",")[1]), self.path.read_bytes())
        self.assertTrue(response.closed)

    def test_status_api_distinguishes_timeout_from_no_transcript(self):
        http, session = transport(requests.Timeout("hidden"))
        text, kind = MiMoASR(http=http).recognize_with_status(
            self.path, retries=1, budget=8)
        self.assertEqual((text, kind), ("", "timeout"))
        self.assertEqual(session.post.call_count, 1)
        self.assertEqual(session.post.call_args.kwargs["timeout"], (8 / 3, 4))

    @mock.patch("mimo_http.time.sleep")
    def test_timeout_is_bounded_and_redacted(self, sleep):
        http, session = transport(requests.Timeout("credential-must-not-appear"), requests.Timeout())
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            self.assertEqual(MiMoASR(http=http).recognize(self.path), "")
        self.assertEqual(session.post.call_count, 2)
        self.assertNotIn("credential-must-not-appear", output.getvalue())

    @mock.patch("mimo_http.time.sleep")
    def test_429_retries_once_then_recovers(self, sleep):
        limited = Response({}, 429)
        limited.headers["Retry-After"] = "10000"
        http, session = transport(limited, Response({"choices": [{"message": {"content": "恢复"}}]}))
        self.assertEqual(MiMoASR(http=http).recognize(self.path), "恢复")
        self.assertTrue(limited.closed)
        self.assertEqual(session.post.call_count, 2)
        self.assertLessEqual(sleep.call_args.args[0], 2)

    def test_invalid_responses_return_empty(self):
        for body in (b"not json", [], {}, {"choices": []},
                     {"choices": [{"message": {"content": None}}]},
                     {"choices": [{"message": {"content": ""}}]},
                     {"choices": [{"finish_reason": "length", "message": {"content": "部分"}}]}):
            with self.subTest(body=body):
                response = Response(body)
                http, _ = transport(response)
                self.assertEqual(MiMoASR(http=http).recognize(self.path), "")
                self.assertTrue(response.closed)

    def test_bad_audio_never_reaches_network(self):
        for data in (b"bad", wav_bytes(24000), wav_bytes(16000, channels=2), wav_bytes(16000)[:-3]):
            self.path.write_bytes(data)
            http, session = transport()
            self.assertEqual(MiMoASR(http=http).recognize(self.path), "")
            session.post.assert_not_called()


class MiMoTTSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "speech.wav"

    def test_nonstream_saves_valid_16k_wav(self):
        response = Response(audio_result())
        http, session = transport(response)
        self.assertTrue(MiMoTTS(http=http).synthesize("你好", self.path))
        pcm, rate = read_wav(self.path.read_bytes(), require_16k=True)
        self.assertEqual(rate, 16000)
        self.assertGreater(len(pcm), 0)
        self.assertEqual(session.post.call_args.kwargs["json"]["messages"][0]["role"], "assistant")
        self.assertTrue(response.closed)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.path])

    @mock.patch("mimo_http.time.sleep")
    def test_nonstream_timeout_and_429_are_bounded(self, sleep):
        for failure in (requests.Timeout(), Response({}, 429)):
            http, session = transport(failure, failure)
            self.assertFalse(MiMoTTS(http=http).synthesize("你好", self.path))
            self.assertFalse(self.path.exists())
            self.assertEqual(session.post.call_count, 2)

    def test_invalid_audio_preserves_previous_file(self):
        self.path.write_bytes(b"previous")
        bodies = ({}, {"choices": [{"message": {"audio": {"data": "!!!"}}}]},
                  audio_result(b"bad"), audio_result(wav_bytes(channels=2)),
                  audio_result(wav_bytes()[:-2]), audio_result(wav_bytes(frames=0)))
        for body in bodies:
            http, _ = transport(Response(body))
            self.assertFalse(MiMoTTS(http=http).synthesize("你好", self.path))
            self.assertEqual(self.path.read_bytes(), b"previous")
        self.assertEqual(len(list(Path(self.tmp.name).iterdir())), 1)

    def test_stream_resampling_preserves_state_across_odd_chunks(self):
        pcm = struct.pack("<" + "h" * 600, *range(600))
        response = Response(sse(audio_event(pcm[:3]), audio_event(pcm[3:101]), audio_event(pcm[101:])), streaming=True)
        http, _ = transport(response)
        engine = MiMoTTS(http=http)
        engine.streaming_enabled = True
        expected = PCM16Resampler(24000).feed(pcm)
        self.assertEqual(b"".join(engine.pcm_stream("你好")), expected)
        self.assertTrue(response.closed)

    def test_first_audio_arrives_before_network_finishes(self):
        response = Response(sse(audio_event(b"\0\0" * 100), audio_event(b"\1\0" * 100)), streaming=True)
        http, _ = transport(response)
        engine = MiMoTTS(http=http)
        engine.streaming_enabled = True
        stream = engine.pcm_stream("你好")
        self.assertTrue(next(stream))
        self.assertFalse(response.closed)
        stream.close()
        self.assertTrue(response.closed)

    def test_before_output_failure_falls_back_to_wav(self):
        first = Response({}, 400)
        second = Response(audio_result())
        http, session = transport(first, second)
        engine = MiMoTTS(http=http)
        engine.streaming_enabled = True
        self.assertTrue(b"".join(engine.pcm_stream("你好")))
        self.assertEqual([call.kwargs["json"]["stream"] for call in session.post.call_args_list], [True, False])
        self.assertTrue(first.closed and second.closed)

    def test_after_output_failure_never_replays(self):
        for failure in (None, requests.Timeout()):
            response = Response(sse(audio_event(b"\0\0" * 100), done=False), streaming=True, failure=failure)
            http, session = transport(response)
            engine = MiMoTTS(http=http)
            engine.streaming_enabled = True
            stream = engine.pcm_stream("你好")
            self.assertTrue(next(stream))
            with self.assertRaises(MiMoError):
                next(stream)
            self.assertEqual(session.post.call_count, 1)
            self.assertTrue(response.closed)

    @mock.patch("mimo_http.time.sleep")
    def test_stream_429_does_not_bypass_limit_by_fallback(self, sleep):
        http, session = transport(Response({}, 429), Response({}, 429))
        engine = MiMoTTS(http=http)
        engine.streaming_enabled = True
        with self.assertRaises(MiMoError):
            list(engine.pcm_stream("你好"))
        self.assertEqual(session.post.call_count, 2)
        self.assertTrue(all(call.kwargs["json"]["stream"] for call in session.post.call_args_list))

    def test_auth_error_is_not_retried(self):
        http, session = transport(Response({}, 401))
        engine = MiMoTTS(http=http)
        engine.streaming_enabled = True
        with self.assertRaises(MiMoError):
            list(engine.pcm_stream("你好"))
        self.assertEqual(session.post.call_count, 1)


class FormatAndTransportTests(unittest.TestCase):
    def test_extended_wav_chunk_is_not_pcm(self):
        data = wav_bytes()
        extra = b"JUNK" + struct.pack("<I", 4) + b"xxxx"
        data = data[:12] + extra + data[12:]
        data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
        self.assertEqual(normalize_wav(data), normalize_wav(wav_bytes()))

    def test_odd_final_pcm_fails(self):
        converter = PCM16Resampler(24000)
        converter.feed(b"\0\0\0")
        with self.assertRaises(AudioFormatError):
            converter.finish()

    def test_failed_conversion_never_calls_aplay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio.wav"
            path.write_bytes(wav_bytes())
            player = object.__new__(AudioPlayer)
            player.backend = "aplay"
            with mock.patch.dict(sys.modules, {"audioop": None}), mock.patch("audio.play.subprocess.run") as run:
                self.assertFalse(player.play(str(path)))
                run.assert_not_called()

    def test_key_and_raw_server_error_not_logged(self):
        http, session = transport(Response({"error": "sensitive-server-body"}, 403))
        with self.assertRaises(MiMoError) as result:
            http.request({})
        self.assertNotIn("sensitive-server-body", str(result.exception))
        self.assertNotIn("offline-placeholder", str(result.exception))
        self.assertFalse(session.post.call_args.kwargs["allow_redirects"])

    def test_credential_cannot_be_sent_to_other_host(self):
        with self.assertRaises(MiMoError):
            MiMoHTTP(api_key="offline-placeholder", url="https://example.org/v1/chat/completions")

    def test_trickle_deadline_closes_response(self):
        response = Response(b"x" * 2048, streaming=True)
        http, _ = transport(response)
        with mock.patch("mimo_http.time.monotonic", side_effect=[0, 0, 2]):
            with self.assertRaises(MiMoError):
                list(http.responses({"stream": True}, budget=1))
        self.assertTrue(response.closed)

    def test_event_size_limit_closes_response(self):
        response = Response(b"data:" + b"x" * 100, streaming=True)
        http, _ = transport(response)
        http.MAX_EVENT = 20
        with self.assertRaises(MiMoError):
            list(http.responses({"stream": True}))
        self.assertTrue(response.closed)

    def test_legacy_configuration_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.py"
            path.write_text("import os\nMIMO_API_KEY = os.getenv('MIMO_API_KEY', 'offline-placeholder')\nraise RuntimeError('must not execute')\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"MIMO_API_KEY": "offline-override"}):
                self.assertEqual(read_local_values(path)["MIMO_API_KEY"], "offline-override")

    def test_llm_partial_eof_raises_instead_of_success(self):
        response = Response(sse({"choices": [{"delta": {"content": "半句"}}]}, done=False), streaming=True)
        http, _ = transport(response)
        llm = MiMoLLM()
        llm.http.close()
        llm.http = http
        stream = llm.chat_stream("测试")
        self.assertEqual(next(stream), "半句")
        with self.assertRaises(MiMoError):
            next(stream)
        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
