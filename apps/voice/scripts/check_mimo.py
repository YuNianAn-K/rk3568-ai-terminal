#!/usr/bin/env python3
"""Opt-in live adapter smoke test; no credentials, transcripts or replies logged."""
import argparse
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (TTS_ENGINE, MIMO_API_KEY, MIMO_MODEL,
                    MIMO_ASR_MODEL, MIMO_TTS_MODEL)
from asr.mimo_asr import MiMoASR
from audio.pcm import read_wav
from audio.play import AudioPlayer
from llm.mimo import MiMoLLM
from tts.mimo_tts import MiMoTTS


def report(stage, start, **metrics):
    fields = "".join("[%s=%s]" % pair for pair in metrics.items())
    print("[MIMO_CHECK][stage=%s][ms=%d]%s" %
          (stage, (time.monotonic() - start) * 1000, fields), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Make billable real API calls with synthetic test content")
    parser.add_argument("--play", action="store_true", help="Also play the short test; stop the normal service first")
    args = parser.parse_args()
    print("[MIMO_CHECK][key_present=%s][asr=%s][tts=%s][llm=%s]" %
          (bool(MIMO_API_KEY), "mimo", TTS_ENGINE, MIMO_MODEL), flush=True)
    print("[MIMO_CHECK][asr_model=%s][tts_model=%s]" % (MIMO_ASR_MODEL, MIMO_TTS_MODEL))
    if not args.online:
        return 0
    if not MIMO_API_KEY:
        print("[MIMO_CHECK][error=missing_key]")
        return 1
    adapters = []
    try:
        tts = MiMoTTS()
        adapters.append(tts)
        asr = MiMoASR()
        adapters.append(asr)
        llm = MiMoLLM()
        adapters.append(llm)
        with tempfile.TemporaryDirectory(prefix="mimo-check-") as directory:
            path = Path(directory) / "sample.wav"
            started = time.monotonic()
            if not tts.synthesize("你好，这是语音测试。", str(path)):
                raise RuntimeError("tts_nonstream_failed")
            pcm, rate = read_wav(path.read_bytes(), require_16k=True)
            report("tts_nonstream", started, rate=rate, frames=len(pcm) // 2)
            started = time.monotonic()
            transcript = asr.recognize(str(path))
            if not transcript or not any(word in transcript for word in ("语音", "测试")):
                raise RuntimeError("asr_content_mismatch")
            report("asr", started, expected_content=True)
            started = time.monotonic()
            answer = []
            for text in llm.chat_stream("请只回答：测试成功"):
                if not answer:
                    report("llm_first_token", started)
                answer.append(text)
            if "测试成功" not in "".join(answer):
                raise RuntimeError("llm_content_mismatch")
            report("llm_end", started, expected_content=True)
            started = time.monotonic()
            counts = {"chunks": 0, "bytes": 0}
            def chunks():
                for chunk in tts.pcm_stream("你好，流式语音测试成功。"):
                    if not counts["chunks"]:
                        report("tts_first_pcm", started, output_rate=16000)
                    counts["chunks"] += 1
                    counts["bytes"] += len(chunk)
                    yield chunk
            stream = chunks()
            try:
                if args.play:
                    if not AudioPlayer().play_pcm_stream(stream):
                        raise RuntimeError("playback_failed")
                else:
                    for _ in stream:
                        pass
            finally:
                stream.close()
            if not counts["bytes"]:
                raise RuntimeError("empty_pcm")
            report("tts_pcm_end", started, **counts, played=args.play)
        print("[MIMO_CHECK][result=PASS]", flush=True)
        return 0
    except Exception as error:
        print("[MIMO_CHECK][result=FAIL][kind=%s][status=%s]" %
              (getattr(error, "kind", type(error).__name__), getattr(error, "status", 0)), flush=True)
        return 1
    finally:
        for adapter in reversed(adapters):
            adapter.close()


if __name__ == "__main__":
    sys.exit(main())
