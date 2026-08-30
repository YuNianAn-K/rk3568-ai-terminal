# AI Voice Terminal - 语音对话实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现唤醒词触发的语音对话：说"你好助手" → 录音 → 百度 ASR → MiMo 对话 → TTS 播放

**Architecture:** 后台线程用 Porcupine 监听唤醒词，触发后 arecord 录音，百度 API 识别文字，MiMo 生成回复，火山引擎 TTS 合成语音，aplay 播放。无麦克风时降级为文字输入。

**Tech Stack:** pvporcupine, pyaudio, arecord (ALSA), 百度语音识别 API, MiMo API, 火山引擎 TTS

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `asr/baidu_asr.py` | 新增 | 百度语音识别：access_token 管理 + 语音转文字 |
| `audio/record.py` | 改造 | ALSA 录音 + 能量检测自动停止 |
| `wake/porcupine.py` | 新增 | Porcupine 唤醒词检测封装 |
| `main.py` | 改造 | 主循环：语音/文字双模式 + 状态提示 + 重试 |
| `config/config.py` | 改造 | 添加百度 ASR 配置项 |
| `requirements.txt` | 改造 | 添加 pvporcupine, pyaudio |
| `scripts/ai-voice.service` | 新增 | systemd 开机自启动 |

---

### Task 1: 百度 ASR 模块

**Files:**
- Create: `asr/__init__.py`
- Create: `asr/baidu_asr.py`
- Modify: `config/config.py`

- [ ] **Step 1: 添加百度 ASR 配置**

在 `config/config.py` 末尾添加：

```python
# Baidu ASR Configuration
BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
```

- [ ] **Step 2: 创建 asr 模块**

创建 `asr/__init__.py`（空文件）。

- [ ] **Step 3: 实现百度 ASR 类**

创建 `asr/baidu_asr.py`：

```python
"""
Baidu Speech Recognition Module
"""
import os
import json
import time
import requests


class BaiduASR:
    """百度语音识别"""

    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    ASR_URL = "https://vop.baidu.com/server_api"

    def __init__(self, api_key: str = None, secret_key: str = None):
        from config import BAIDU_API_KEY, BAIDU_SECRET_KEY
        self.api_key = api_key or BAIDU_API_KEY
        self.secret_key = secret_key or BAIDU_SECRET_KEY
        self.access_token = None
        self.token_expire = 0

    def _get_access_token(self) -> str:
        """获取百度 access_token，自动缓存和续期"""
        if self.access_token and time.time() < self.token_expire:
            return self.access_token

        resp = requests.post(self.TOKEN_URL, params={
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.token_expire = time.time() + data.get("expires_in", 2592000) - 60
        return self.access_token

    def recognize(self, audio_file: str, retries: int = 3) -> str:
        """
        识别 WAV 文件中的语音

        Args:
            audio_file: WAV 文件路径（16kHz, 16bit, mono）
            retries: 重试次数

        Returns:
            识别出的文字，失败返回空字符串
        """
        token = self._get_access_token()

        with open(audio_file, "rb") as f:
            audio_data = f.read()

        for attempt in range(retries):
            try:
                resp = requests.post(
                    f"{self.ASR_URL}?cuid=ai_voice&token={token}&dev_pid=1537",
                    headers={"Content-Type": "audio/wav;rate=16000"},
                    data=audio_data,
                    timeout=15,
                )
                resp.raise_for_status()
                result = resp.json()

                if result.get("err_no") == 0:
                    return "".join(result.get("result", []))
                elif result.get("err_no") == 110:
                    # Token 过期，刷新重试
                    self.access_token = None
                    token = self._get_access_token()
                    continue
                else:
                    print(f"ASR error: {result.get('err_msg', 'unknown')}")
                    return ""

            except requests.exceptions.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                print(f"ASR request failed: {e}")
                return ""

        return ""


# Test
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python baidu_asr.py <audio_file>")
        sys.exit(1)
    asr = BaiduASR()
    text = asr.recognize(sys.argv[1])
    print(f"Result: {text}")
```

- [ ] **Step 4: 本地验证（可选）**

如果已有百度 API Key，可以用录制好的 WAV 文件测试：
```bash
cd D:\AProject\rk3568-ai-terminal\apps\voice
set BAIDU_API_KEY=xxx
set BAIDU_SECRET_KEY=xxx
py asr\baidu_asr.py D:\tmp\ai_voice\audio\test.wav
```
没有 Key 则跳过，后续部署时再测。

- [ ] **Step 5: Commit**

```bash
git add asr/ config/config.py
git commit -m "feat: add Baidu ASR module for speech recognition"
```

---

### Task 2: 录音模块

**Files:**
- Modify: `audio/record.py`（替换现有 play.py 的内容，或新建 record.py）
- Create: `audio/__init__.py`

- [ ] **Step 1: 创建 audio 包**

创建 `audio/__init__.py`（空文件，如果还没有）。

- [ ] **Step 2: 实现录音模块**

创建 `audio/record.py`：

```python
"""
Audio Recording Module - ALSA recording with silence detection
"""
import os
import subprocess
import struct
import tempfile


class AudioRecorder:
    """ALSA 录音，支持静音自动停止"""

    def __init__(self, sample_rate=16000, channels=1, silence_threshold=500, max_seconds=10):
        self.sample_rate = sample_rate
        self.channels = channels
        self.silence_threshold = silence_threshold
        self.max_seconds = max_seconds
        self.has_mic = self._check_microphone()

    def _check_microphone(self) -> bool:
        """检测麦克风是否可用"""
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True, timeout=5
            )
            return b"card" in result.stdout
        except Exception:
            return False

    def record_to_file(self, output_file: str = None) -> str:
        """
        录音到文件，静音自动停止

        Args:
            output_file: 输出文件路径，None 则自动创建临时文件

        Returns:
            录音文件路径，失败返回空字符串
        """
        if not self.has_mic:
            print("No microphone detected")
            return ""

        output_file = output_file or tempfile.mktemp(suffix=".wav")

        try:
            # arecord 录音，-d 限制最大时长
            result = subprocess.run(
                [
                    "arecord",
                    "-f", "S16_LE",          # 16bit little endian
                    "-r", str(self.sample_rate),
                    "-c", str(self.channels),
                    "-d", str(self.max_seconds),
                    "-t", "wav",
                    output_file,
                ],
                capture_output=True,
                timeout=self.max_seconds + 5,
            )

            if result.returncode != 0:
                print(f"arecord error: {result.stderr.decode()}")
                return ""

            # 检查文件是否有效
            if os.path.exists(output_file) and os.path.getsize(output_file) > 44:
                return output_file
            else:
                print("Recording too short or invalid")
                return ""

        except subprocess.TimeoutExpired:
            # 超时是正常的（达到最大时长）
            if os.path.exists(output_file) and os.path.getsize(output_file) > 44:
                return output_file
            return ""
        except Exception as e:
            print(f"Recording error: {e}")
            return ""

    def record_interactive(self) -> str:
        """
        交互式录音：按 Enter 开始，再按 Enter 停止

        Returns:
            录音文件路径
        """
        if not self.has_mic:
            print("No microphone detected, using text input mode")
            return ""

        input("Press Enter to start recording...")
        print("Recording... (press Enter to stop)")

        output_file = tempfile.mktemp(suffix=".wav")

        # 启动 arecord 后台进程
        proc = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", str(self.channels),
                "-t", "wav",
                output_file,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 等待用户按 Enter 停止
        input()
        proc.terminate()
        proc.wait(timeout=5)

        if os.path.exists(output_file) and os.path.getsize(output_file) > 44:
            return output_file
        return ""


# Test
if __name__ == "__main__":
    recorder = AudioRecorder()
    print(f"Microphone available: {recorder.has_mic}")
    if recorder.has_mic:
        print("Testing 3-second recording...")
        result = recorder.record_to_file()
        if result:
            print(f"Recorded: {result} ({os.path.getsize(result)} bytes)")
        else:
            print("Recording failed")
```

- [ ] **Step 3: 保留原有 play.py**

`audio/play.py` 保持不变，录音和播放是两个独立模块。

- [ ] **Step 4: 板子验证（无麦克风时）**

```bash
ssh root@172.20.10.10 "cd ~/AI_voice && PYTHONPATH=. python3 -c 'from audio.record import AudioRecorder; r = AudioRecorder(); print(f\"Mic: {r.has_mic}\")'"
```
预期输出：`Mic: False`（因为还没插麦克风）

- [ ] **Step 5: Commit**

```bash
git add audio/record.py audio/__init__.py
git commit -m "feat: add ALSA audio recording with silence detection"
```

---

### Task 3: Porcupine 唤醒词模块

**Files:**
- Create: `wake/__init__.py`
- Create: `wake/porcupine.py`
- Modify: `config/config.py`

- [ ] **Step 1: 添加 Porcupine 配置**

在 `config/config.py` 末尾添加：

```python
# Wake Word Configuration
WAKE_WORD = "你好助手"
WAKE_PORCUPINE_ACCESS_KEY = os.getenv("WAKE_PORCUPINE_ACCESS_KEY", "")
```

- [ ] **Step 2: 创建 wake 包**

创建 `wake/__init__.py`（空文件）。

- [ ] **Step 3: 实现唤醒词检测**

创建 `wake/porcupine.py`：

```python
"""
Wake Word Detection Module - Porcupine-based wake word listener
"""
import os
import sys
import struct


class WakeWordDetector:
    """Porcupine 唤醒词检测"""

    def __init__(self, keyword: str = None, access_key: str = None):
        from config import WAKE_WORD, WAKE_PORCUPINE_ACCESS_KEY
        self.keyword = keyword or WAKE_WORD
        self.access_key = access_key or WAKE_PORCUPINE_ACCESS_KEY
        self.porcupine = None
        self.mic = None
        self.available = self._check_availability()

    def _check_availability(self) -> bool:
        """检查 Porcupine 和麦克风是否可用"""
        try:
            import pvporcupine
            self.pvporcupine = pvporcupine
        except ImportError:
            print("pvporcupine not installed, wake word disabled")
            return False

        if not self.access_key:
            print("No Porcupine access key, wake word disabled")
            return False

        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            # 检查是否有麦克风
            if pa.get_device_count() == 0:
                pa.terminate()
                print("No audio device, wake word disabled")
                return False
            pa.terminate()
        except ImportError:
            print("pyaudio not installed, wake word disabled")
            return False

        return True

    def listen(self, callback):
        """
        持续监听唤醒词，检测到后调用 callback

        Args:
            callback: 唤醒时调用的函数，无参数
        """
        if not self.available:
            print("Wake word detector not available")
            return

        import pvporcupine
        import pyaudio

        self.porcupine = pvporcupine.create(
            access_key=self.access_key,
            keywords=[self.keyword],
        )

        pa = pyaudio.PyAudio()
        self.mic = pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length,
        )

        print(f"Listening for '{self.keyword}'...")

        try:
            while True:
                pcm = self.mic.read(self.porcupine.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                result = self.porcupine.process(pcm)
                if result >= 0:
                    print(f"Wake word detected!")
                    callback()
        except KeyboardInterrupt:
            pass
        finally:
            if self.mic:
                self.mic.close()
            if self.porcupine:
                self.porcupine.delete()
            pa.terminate()

    def stop(self):
        """停止监听"""
        if self.mic:
            self.mic.close()
        if self.porcupine:
            self.porcupine.delete()


# Test
if __name__ == "__main__":
    detector = WakeWordDetector()
    print(f"Available: {detector.available}")
    if detector.available:
        print("Starting wake word detection (Ctrl+C to stop)...")
        detector.listen(lambda: print("Triggered!"))
```

- [ ] **Step 4: 本地验证（可选）**

需要先注册 Picovoice 获取免费 access key：
- 注册 https://console.picovoice.ai/
- 获取 Porcupine Access Key
- 设置环境变量后测试

没有 key 则跳过，后续配置。

- [ ] **Step 5: Commit**

```bash
git add wake/ config/config.py
git commit -m "feat: add Porcupine wake word detection module"
```

---

### Task 4: 主程序改造

**Files:**
- Modify: `main.py`
- Modify: `config/config.py`

- [ ] **Step 1: 改造主程序**

用以下内容替换 `main.py`：

```python
#!/usr/bin/env python3
"""
AI Voice Terminal - Main Application
RK3568 AI Voice Terminal with voice dialogue support
"""
import sys
import os
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.mimo import MiMoLLM
from tts.tts import TTSEngine
from audio.play import AudioPlayer
from audio.record import AudioRecorder
from asr.baidu_asr import BaiduASR


class AIVoiceTerminal:
    def __init__(self):
        print("Initializing AI Voice Terminal...")
        self.llm = MiMoLLM()
        self.tts = TTSEngine()
        self.player = AudioPlayer()
        self.recorder = AudioRecorder()
        self.asr = BaiduASR()
        self.history = []
        self.max_response_chars = 500

        # Check wake word availability
        self.wake_detector = None
        try:
            from wake.porcupine import WakeWordDetector
            self.wake_detector = WakeWordDetector()
        except Exception as e:
            print(f"Wake word disabled: {e}")

        print(f"Microphone: {'available' if self.recorder.has_mic else 'not detected (text mode)'}")
        print(f"Wake word: {'available' if self.wake_detector and self.wake_detector.available else 'disabled'}")
        print("Initialization complete!\n")

    def process_input(self, user_input: str):
        """Process user input and generate response with voice"""
        if not user_input or not user_input.strip():
            return

        print(f"\nYou: {user_input}")

        # Call MiMo API with retry
        print("Thinking...", end=" ", flush=True)
        response = self._call_llm_with_retry(user_input)
        print(f"done")

        # Truncate if too long for TTS
        if len(response) > self.max_response_chars:
            response = response[:self.max_response_chars] + "..."

        print(f"\nMiMo: {response}")

        # Add to history
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": response})

        # Keep history manageable
        if len(self.history) > 20:
            self.history = self.history[-20:]

        # TTS and play
        print("Synthesizing speech...", end=" ", flush=True)
        audio_file = self.tts.text_to_speech(response)

        if audio_file:
            print("done")
            print("Playing...")
            self.player.play(audio_file)
        else:
            print("TTS failed, text shown above")

    def _call_llm_with_retry(self, user_input: str, retries: int = 3) -> str:
        """Call MiMo with exponential backoff retry"""
        for attempt in range(retries):
            response = self.llm.chat(user_input, self.history)
            if not response.startswith("API调用失败") and not response.startswith("API响应格式错误"):
                return response
            if attempt < retries - 1:
                import time
                wait = 2 ** attempt
                print(f"retry in {wait}s...", end=" ", flush=True)
                time.sleep(wait)
        return response  # Return last response even if failed

    def _voice_mode(self):
        """Voice dialogue mode - wake word triggered"""
        if not self.wake_detector or not self.wake_detector.available:
            return False

        def on_wake():
            print("\nListening... (speak now)")
            audio_file = self.recorder.record_to_file()
            if not audio_file:
                print("Recording failed")
                return

            print("Recognizing...", end=" ", flush=True)
            text = self.asr.recognize(audio_file)
            print("done")

            if text:
                self.process_input(text)
            else:
                print("Could not understand, try again")

        self.wake_detector.listen(on_wake)
        return True

    def _text_mode(self):
        """Text input mode - fallback when no microphone"""
        print("=" * 50)
        print("AI Voice Terminal - Text Mode")
        print("Type your message and press Enter.")
        print("Type 'quit' or 'exit' to exit.")
        print("=" * 50)

        while True:
            try:
                user_input = input("\nYou: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nGoodbye!")
                    break
                self.process_input(user_input)
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break

    def run(self):
        """Run the terminal - voice or text mode"""
        # Try voice mode first
        if self.recorder.has_mic and self.wake_detector and self.wake_detector.available:
            print("=" * 50)
            print("AI Voice Terminal - Voice Mode")
            print(f"Say '{self.wake_detector.keyword}' to start")
            print("Press Ctrl+C to exit")
            print("=" * 50)
            self._voice_mode()
        else:
            self._text_mode()


def main():
    """Main entry point"""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\nGoodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        terminal = AIVoiceTerminal()
        terminal.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 本地验证**

```bash
cd D:\AProject\rk3568-ai-terminal\apps\voice
py main.py
```
预期：显示文字模式界面，可以输入文字对话。

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: refactor main.py with voice/text dual mode and status prompts"
```

---

### Task 5: 部署到板子

**Files:**
- Modify: 板子 `~/AI_voice/` 所有文件

- [ ] **Step 1: 同步代码到板子**

```bash
scp -r D:/AProject/rk3568-ai-terminal/apps/voice/* root@172.20.10.10:~/AI_voice/
```

- [ ] **Step 2: 板子安装依赖**

```bash
ssh root@172.20.10.10 "cd ~/AI_voice && pip3 install pvporcupine pyaudio 2>&1 | tail -5"
```

注意：pyaudio 可能需要编译，如果失败先装系统依赖：
```bash
ssh root@172.20.10.10 "apt-get install -y portaudio19-dev 2>/dev/null; pip3 install pyaudio"
```
Buildroot 可能没有 apt-get，如果 pyaudio 装不上，用文字模式先跑通。

- [ ] **Step 3: 板子测试文字模式**

```bash
ssh root@172.20.10.10 "cd ~/AI_voice && PYTHONPATH=. python3 main.py"
```
输入文字测试对话和 TTS 播放。

- [ ] **Step 4: 验证百度 ASR（有 Key 时）**

```bash
ssh root@172.20.10.10 "cd ~/AI_voice && PYTHONPATH=. python3 -c \"
from asr.baidu_asr import BaiduASR
asr = BaiduASR()
print(f'Token available: {bool(asr._get_access_token())}')
\""
```

- [ ] **Step 5: Commit**

无代码改动，跳过。

---

### Task 6: 开机自启动

**Files:**
- Create: `scripts/ai-voice.service`

- [ ] **Step 1: 创建 systemd service 文件**

创建 `scripts/ai-voice.service`：

```ini
[Unit]
Description=AI Voice Terminal
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/AI_voice
ExecStart=/usr/bin/python3 /root/AI_voice/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONPATH=/root/AI_voice

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: 部署到板子**

```bash
scp D:/AProject/rk3568-ai-terminal/apps/voice/scripts/ai-voice.service root@172.20.10.10:/etc/systemd/system/
ssh root@172.20.10.10 "systemctl daemon-reload && systemctl enable ai-voice"
```

- [ ] **Step 3: 测试启停**

```bash
ssh root@172.20.10.10 "systemctl start ai-voice && sleep 2 && systemctl status ai-voice"
```
预期：active (running)

```bash
ssh root@172.20.10.10 "systemctl stop ai-voice"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ai-voice.service
git commit -m "feat: add systemd service for auto-start on boot"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 板子完整流程测试**

文字模式（无麦克风）：
```bash
ssh root@172.20.10.10 "cd ~/AI_voice && PYTHONPATH=. python3 main.py"
```
输入"你好"，确认：MiMo 回复 → TTS 合成 → 喇叭播放。

- [ ] **Step 2: 自启动测试**

```bash
ssh root@172.20.10.10 "systemctl start ai-voice && journalctl -u ai-voice -f"
```
观察日志，确认程序正常启动。Ctrl+C 退出日志查看。

- [ ] **Step 3: 最终清理**

确认无调试代码残留，代码可正常运行。
