"""Credential-safe voice settings; legacy local values are parsed, never executed."""
import ast
import os
from pathlib import Path
import tempfile


def read_local_values(path):
    """Read scalar settings without executing mkdir, imports or arbitrary code.

    Only the literal/os.getenv forms used by the historical local config are
    supported. New deployments need only environment variables.
    """
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, SyntaxError, UnicodeError):
        raise ValueError("Local voice configuration cannot be parsed") from None
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant):
            values[target.id] = value.value
        elif (isinstance(value, ast.Call) and
              isinstance(value.func, ast.Attribute) and
              isinstance(value.func.value, ast.Name) and
              value.func.value.id == "os" and value.func.attr == "getenv" and
              not value.keywords and 1 <= len(value.args) <= 2 and
              all(isinstance(arg, ast.Constant) for arg in value.args) and
              isinstance(value.args[0].value, str)):
            fallback = value.args[1].value if len(value.args) == 2 else None
            values[target.id] = os.getenv(value.args[0].value, fallback)
    return values


_local = read_local_values(os.getenv(
    "VOICE_LOCAL_CONFIG", str(Path(__file__).with_name("config.py"))))


def _setting(name, default=""):
    return os.environ.get(name, _local.get(name, default))


# MiMo is the only ASR provider. TTS and LLM retain explicit optional engines.
TTS_ENGINE = os.getenv("VOICE_TTS_ENGINE", "mimo")
LLM_ENGINE = os.getenv("LLM_ENGINE", "mimo")
MIMO_API_KEY = _setting("MIMO_API_KEY")
MIMO_API_URL = _setting("MIMO_API_URL", "https://api.xiaomimimo.com/v1/chat/completions")
MIMO_MODEL = _setting("MIMO_MODEL", "mimo-v2.5")
MIMO_ASR_MODEL = "mimo-v2.5-asr"
MIMO_TTS_MODEL = "mimo-v2.5-tts"
MIMO_TTS_VOICE = _setting("MIMO_TTS_VOICE", "mimo_default")
MIMO_TTS_STREAM = str(_setting("MIMO_TTS_STREAM", "1")).lower() in ("1", "true", "yes")
MIMO_THINKING = _setting("MIMO_THINKING", "disabled")
MIMO_ASR_LANGUAGE = _setting("MIMO_ASR_LANGUAGE", "auto")
VOICE_LOCAL_RESPONSES = str(_setting("VOICE_LOCAL_RESPONSES", "1")).lower() in ("1", "true", "yes")

# Preserve non-secret recording constraints and the optional GLM LLM engine.
HIGH_PASS_ENABLE = str(_setting("HIGH_PASS_ENABLE", "true")).lower() in ("1", "true", "yes")
HIGH_PASS_CUTOFF = int(_setting("HIGH_PASS_CUTOFF", 80))
WAKE_WORD = "小爱同学"
# Opt in only after the matching local model/runtime have been installed.
VOICE_WAKE_ENABLE = str(_setting("VOICE_WAKE_ENABLE", "0")).lower() in ("1", "true", "yes")
VOICE_WAKE_MODEL_PATH = _setting("VOICE_WAKE_MODEL_PATH", "/opt/ai-voice-wake/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20")
GLM_API_KEY = _setting("GLM_API_KEY")
GLM_API_URL = _setting("GLM_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_MODEL = _setting("GLM_MODEL", "glm-4-flash")
TTS_VOICE = _setting("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_RATE = _setting("TTS_RATE", "+0%")
TTS_VOLUME = _setting("TTS_VOLUME", "+0%")
AUDIO_FILE = os.path.join(tempfile.gettempdir(), "ai_voice", "reply.wav")
del _local
__all__ = [name for name in globals() if name.isupper()]
