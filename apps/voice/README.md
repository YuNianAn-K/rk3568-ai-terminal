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
├── wake/                # 本地中文关键词检测；英文历史入口不启用
├── scripts/             # Buildroot 启动、检查与调试脚本
├── tests/               # 离线单元测试
└── config/              # 本地配置；真实 config.py 不进入 Git
```

## 当前运行方式

- 正式板端服务：`voice_service.py`，由 Buildroot 脚本 `scripts/S99ai-voice` 启动。
- Qt 通信：JSON Lines over AF_UNIX，Socket 为 `/tmp/ai-voice.sock`。
- 支持命令：`status`、`start`、`stop`、`cancel`；同一时间只允许一轮语音任务。
- 中文唤醒候选额外支持 `wake_enable`、`wake_disable`；旧命令和事件格式不变。
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

## PC13 断网固定语音控制

联网时仍优先使用 MiMo ASR。无默认网络路由时直接在同一份 16 kHz
录音上运行本地识别；云端识别失败时也会在有界等待后回退，并短暂冷却
失败请求。网络路由恢复后的下一轮重新尝试 MiMo。离线只接受完整的
“打开指示灯”“关闭指示灯”“查询指示灯状态”；低置信度、否定、冲突或
其他文本不触发串口。开关必须通过 `OK` 和 `LED?` 回读验证，查询只信任
`LED?`；离线回复在现有 Qt Socket 上显示文字，不依赖云端 TTS。

板端模型为 [Vosk 官方 small-cn-0.22](https://alphacephei.com/vosk/models/)
（Apache 2.0，压缩包约 42 MB，解压约 66 MB），运行于
`/opt/ai-voice-offline/vosk-model-small-cn-0.22`；ARM64 Python wheel
`vosk==0.3.45` 与所需的 `srt` 放在 `/root/AI_voice/vendor`，不入 Git。
模型首次离线使用时加载并在服务进程内复用。模型缺失、音频格式错误或
识别不确定时仅显示失败/重试提示，不会执行控制。现场语音、物理灯和
断网后网络恢复验收结果应单独记录，不得用单元测试代替。

## 后续重点

2026-10-03 语音人物跟随已部署且用户基础实物反馈有效；联网/离线分项未完整验收。
完整的“开始跟踪人物”“停止跟踪”
由固定意图路由发送至运行中的云台应用 `/tmp/gimbal-tracking.sock`，不调用 LLM 决定运动，
不打开 UART。开始只在云台页已开启人物检测并选中新鲜目标、相机/位置可用时执行；
多人未选择目标时提示点框，位置未知时提示回中位，语音不自动回中位。
只有匹配请求编号的 ARM / 双轴 OFF 回执才报告成功；超时显示未确认，不自动重试。
离线语法加入人物启停及否定/疑问候选，词表已核对，保留原置信度门槛；真实识别率待验收。
完整接口及板屏流程见 `../qt-ui/gimbal-joystick/VOICE_TRACKING.md`。

1. 在板端完成 MiMo 三模型权限和真实麦克风闭环验收。
2. 由凭据所有者在对应平台撤销已退役的百度、火山凭据。
3. 记录真实首句播放与完整回答耗时。
4. 2026-10-05 中文唤醒与免按键候选已接入真实服务及两个 Qt 客户端，本地验证通过，等待部署确认。
   模型、依赖、部署与验收边界见 [中文唤醒接入](docs/chinese-wake.md)。按键作为后备入口保留。
