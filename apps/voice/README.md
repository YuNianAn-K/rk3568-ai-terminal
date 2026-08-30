# RK3568 AI 语音服务

本目录是 RK3568 AI 终端的 Python 语音子项目。当前实现以板载麦克风和扬声器为入口，完成录音、百度 ASR、MiMo/GLM 适配、工具调用、流式回答、火山 TTS 与 ALSA 播放，并通过本地 Socket 为 Qt 应用提供状态和控制。

## 目录结构

```text
apps/voice/
├── main.py              # 语音链路与直接运行入口
├── voice_service.py     # Qt 后台服务，监听 /tmp/ai-voice.sock
├── asr/                 # 百度语音识别
├── audio/               # ALSA 录音、播放和音频保护
├── llm/                 # MiMo/GLM 适配与流式接口
├── tools/               # 时间、天气等受控工具调用
├── tts/                 # 语音合成
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

`config/config.py` 可能包含历史真实凭据，已由仓库根 `.gitignore` 排除。不要打印、复制、提交或覆盖板端本地配置。新凭据应通过环境变量或未提交的本地配置提供，并轮换所有曾写入历史文件的密钥。

## 已验证能力

- 连续真实录音、ASR、LLM、TTS 和播放可完成并回到待机。
- Qt 客户端能显示状态、识别文本、流式回答和诊断耗时。
- 录音取消、自动收尾、服务重启和 Qt 自动重连已验证。
- 时间与天气工具调用已接入；普通对话保留流式快速路径。

## 后续重点

1. 迁移并轮换历史凭据。
2. 记录真实首句播放与完整回答耗时。
3. 做短周期多轮稳定性验证。
4. 评估唤醒词，并保留按键作为可靠后备入口。
