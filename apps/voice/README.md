# RK3568 AI 语音服务

本目录是 RK3568 AI 终端的 Python 语音子项目。默认链路为录音、MiMo ASR、MiMo 对话、MiMo TTS 与 ALSA 播放，并通过本地 Socket 为 Qt 应用提供状态和控制。

## 目录结构

```text
apps/voice/
├── main.py              # 语音链路与直接运行入口
├── voice_service.py     # Qt 后台服务，监听 /tmp/ai-voice.sock
├── asr/                 # MiMo ASR 适配器
├── audio/               # ALSA 录音、播放和音频保护
├── llm/                 # MiMo/GLM 适配与流式接口
├── tools/               # 时间、天气等受控工具调用
├── tts/                 # MiMo 流式 TTS 与可选本地/通用 TTS
├── wake/                # 唤醒词实验入口
├── scripts/             # Buildroot 启动、检查与调试脚本
├── tests/               # 离线单元测试
└── config/              # 本地配置；真实 config.py 不进入 Git
```

## 当前运行方式

- 正式板端服务：`voice_service.py`，由 Buildroot 脚本 `scripts/S99ai-voice` 启动。
- Qt 通信：JSON Lines over AF_UNIX，Socket 为 `/tmp/ai-voice.sock`。
- 支持命令：`status`、`start`、`stop`、`cancel`；同一时间只允许一轮语音任务。
- `main.py` 可用于直接调试语音链路，普通对话走流式输出，时间/天气意图走受控工具路径。
- 音频输入输出优先统一为 16 kHz，避免 RK817 codec 在采样率切换后锁死。

## Windows 离线验证

以下命令不调用外部 API：

```powershell
# [Windows]
cd D:\AProject\rk3568-ai-terminal
py -m compileall -q apps\voice
py -m unittest discover -s apps\voice\tests -p "test_*.py"
```

## 板端运行

板端正式部署目录仍为 `/root/AI_voice`：

```bash
# [开发板] 查询 Buildroot 服务状态
/etc/init.d/S99ai-voice status

# [开发板] 前台调试服务；运行前先停止后台实例
cd /root/AI_voice
python3 -u voice_service.py
```

开发板和 VM 使用 DHCP。部署、SSH 或 MQTT 联调前必须重新确认地址，不使用文档里的历史 IP 作为固定值。

## 配置与安全

默认提供方是 `mimo`，所需模型固定为 `mimo-v2.5-asr`、`mimo-v2.5`、`mimo-v2.5-tts`。同一 `MIMO_API_KEY` 用于三种模型，但账号仍需实际具备对应权限。

`config/config.py` 可能包含历史真实凭据，已由仓库根 `.gitignore` 排除。代码只解析其中受支持的标量配置，不执行该文件。新部署优先从 `MIMO_API_KEY` 环境变量取值，也可以通过 `VOICE_LOCAL_CONFIG` 指向一个未提交的本地配置文件。不要打印、复制、提交或覆盖板端本地配置。

MiMo TTS 默认使用流式 PCM，服务端不支持流式或在首帧前返回无效响应时自动降级为非流式 WAV；音频一旦开始播放就不会重试或重放。无论服务端返回 24/48 kHz，ALSA 前都必须转换为单声道 PCM16 16 kHz。

迁移验证、部署前检查和回滚命令见 `docs/mimo-migration.md`。

## 已验证能力

- 连续真实录音、ASR、LLM、TTS 和播放可完成并回到待机。
- Qt 客户端能显示状态、识别文本、流式回答和诊断耗时。
- 录音取消、自动收尾、服务重启和 Qt 自动重连已验证。
- 时间与天气工具调用已接入；普通对话保留流式快速路径。

## 后续重点

1. 在板端完成 MiMo 三模型权限和真实麦克风闭环验收。
2. 由凭据所有者在对应平台撤销已退役的百度、火山凭据。
3. 记录真实首句播放与完整回答耗时。
4. 评估唤醒词，并保留按键作为可靠后备入口。
