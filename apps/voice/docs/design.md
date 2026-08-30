# AI Voice Terminal - 三项优化设计

## 目标

1. **语音对话** — 唤醒词触发 → 录音 → 语音识别 → MiMo 对话 → TTS 播放
2. **交互优化** — 状态提示、异常重试、优雅退出
3. **开机自启动** — systemd service，开机即可用

## 架构

```
用户说话 → Porcupine(唤醒词) → arecord(录音) → 百度ASR(识别) → MiMo(对话) → 火山引擎TTS → aplay(播放)
                ↑                                                              ↓
            后台持续监听                                                喇叭出声
```

## 组件设计

### 1. 唤醒词检测 — `wake/porcupine.py`

- **引擎**: Picovoice Porcupine（免费层：3个自定义唤醒词，1000次/月）
- **唤醒词**: "你好助手"（中文）
- **运行方式**: 后台线程持续监听麦克风，检测到唤醒词后触发回调
- **音频**: 16kHz, 16bit, mono, 512 samples/frame
- **依赖**: `pvporcupine` + `pyaudio`

### 2. 录音模块 — `audio/record.py`

- **引擎**: ALSA arecord（板子自带）
- **触发**: 唤醒词检测回调启动录音
- **停止**: 检测到安静（能量阈值）或最大时长（10秒）自动停止
- **格式**: WAV, 16kHz, 16bit, mono
- **降级**: 麦克风不可用时，自动切换为文字输入模式

### 3. 语音识别 — `asr/baidu_asr.py`

- **服务**: 百度语音识别 REST API
- **认证**: API Key + Secret Key → 获取 access_token
- **音频**: 上传 WAV 文件，返回识别文字
- **限流**: 免费层 QPS=1，够用
- **错误处理**: 网络超时自动重试3次

### 4. 交互优化 — 改造 `main.py`

- **状态提示**: "正在思考..." / "正在合成语音..." / "正在识别..."
- **异常重试**: API 调用失败自动重试3次，间隔 1s/2s/4s
- **回复截断**: MiMo 回复超过500字自动截断（TTS 字符限制）
- **双模式**: 语音模式（唤醒词触发）/ 文字模式（直接输入），自动降级
- **退出**: Ctrl+C 或说"退出"优雅退出，释放资源

### 5. 开机自启动 — `scripts/ai-voice.service`

- systemd service，开机启动 main.py
- 日志输出到 journalctl
- 崩溃自动重启

## 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `wake/porcupine.py` | 新增 | Porcupine 唤醒词检测 |
| `asr/baidu_asr.py` | 新增 | 百度语音识别 |
| `audio/record.py` | 新增 | ALSA 录音（含能量检测） |
| `main.py` | 改造 | 主程序，集成语音流程 |
| `config/config.py` | 改造 | 添加百度 ASR 配置 |
| `requirements.txt` | 改造 | 添加新依赖 |
| `scripts/ai-voice.service` | 新增 | systemd 服务 |

## 配置项

```python
# 百度 ASR
BAIDU_API_KEY = ""       # 控制台获取
BAIDU_SECRET_KEY = ""    # 控制台获取

# 唤醒词
WAKE_WORD = "你好助手"
WAKE_PORCUPINE_ACCESS_KEY = ""  # Porcupine access key

# 录音
RECORD_SAMPLE_RATE = 16000
RECORD_CHANNELS = 1
RECORD_MAX_SECONDS = 10
RECORD_SILENCE_THRESHOLD = 500  # 能量阈值
```

## 依赖

```
pvporcupine    # 唤醒词引擎
pyaudio        # 麦克风音频流
requests       # HTTP 请求（已有）
```

## 交互流程

```
1. 程序启动 → 初始化各模块 → 后台监听麦克风
2. 用户说"你好助手" → Porcupine 检测到 → 提示音
3. 开始录音（最大10秒）→ 检测到安静自动停止
4. 录音文件发送百度 ASR → 返回文字
5. 文字发送 MiMo → 获取回复
6. 回复发送火山引擎 TTS → 合成语音
7. aplay 播放 → 回到监听状态
```

## 降级策略

- 麦克风不可用 → 文字输入模式（终端打字）
- 百度 ASR 失败 → 提示"语音识别失败，请输入文字"
- MiMo 失败 → 提示错误，继续运行
- TTS 失败 → 只显示文字回复
