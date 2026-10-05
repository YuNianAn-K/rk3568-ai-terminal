# RK3568 模块架构与现状

更新时间：2026-09-30（按仓库与任务验收记录同步）

## 状态标签

- **已确认实现**：已有实现，且已完成文档记录的构建、部署、冒烟或真实运行验证。
- **存在代码但尚未现场验收**：实现或部署已完成，但当前任务仍要求在真实板屏或真实场景完成验收。
- **规划中/未实现**：仅有方向、目录入口或设计意图，不代表已有可运行功能。

## 当前模块关系

```text
板载麦克风/扬声器
        │
        ▼
Voice Python 服务 ── AF_UNIX /tmp/ai-voice.sock ── Qt aivoice
        │                                              │
        ├── MiMo 联网 ASR / LLM / TTS                    └── SystemUI 生命周期接入
        ├── 离线固定指令（阶段性可用）
        └── 受控 Action / 时间、天气工具

USB UVC Camera → Qt 云台摄像 / 同帧预览
                       │
                       ▼
        TFLite 手掌检测（CPU） → 有界跟踪控制
          Person 检测尚未接入         │
                                    ▼
RK3568 /dev/ttyS9 ── UART9 M1 / USART1 ── STM32F103C8T6
                                             ├── PC13 LED（已现场验证）
                                             └── 双轴 MG90S（已有手掌跟踪原型）

ConnMan ── ConnmanWifiController ── Settings / SystemUI Wi-Fi 状态层

VM Mosquitto Broker ←── 已验证的板端 MQTT pub/sub ──（业务模块尚未实现）
```

## Voice

### 已确认实现

- 当前联网语音链路已覆盖录音、MiMo ASR/LLM/TTS 与 ALSA 播放；历史百度 ASR、火山 TTS 接入不再代表当前部署链路。
- 联网语音经白名单 Action、UART 回执及状态回读控制 STM32 PC13，用户已目视确认亮灭。
- 无 TTY 服务通过 `/tmp/ai-voice.sock` 提供 `status`、`start`、`stop`、`cancel`，并支持单轮互斥、客户端重连与状态事件。
- Qt aivoice 已通过 `QLocalSocket` 显示语音状态、识别文本、流式回答与诊断信息。
- 16 kHz 音频约束、录音异常恢复、临时文件清理、播放超时与短周期恢复已完成验证。
- 普通对话走流式路径，显式时间/天气意图走工具路径。离线固定语音已达阶段展示可用：语音任务 2026-09-26 覆盖 Wi-Fi 在线但无互联网，4 轮灯控约 0.6–0.8 秒完成回读，1 轮未匹配未动作，恢复联网后对话正常。

### 存在代码但尚未现场验收

- 离线固定语音仍有偶发拒识，其他网络故障下的降级与长期重复性未完全覆盖；已有快速降级场景不必重复推倒验证。
- 流式首 token、首句 TTS、首次播放与端到端耗时，以及短周期多轮/降级行为仍需按 `STATUS.md` 补充现场基线。

### 规划中/未实现

- 唤醒词尚未接入当前 Qt 交互流程；按键仍是可靠入口。
- 中文“小爱同学”已在语音窗口讨论，当前停在诊断录音准备；独立 `tools/gimbal_action.py` 已有短时白名单动作代码，但未接入 `main.py` 语音路由，也不具备人物跟踪启停接口。

## Qt UI

### 已确认实现

- `aivoice` Qt Quick 应用、桌面图标、SystemUI 生命周期接入、AArch64 构建和板端启动均已验证。
- 语音 UI 与 Python 服务的 Socket 协议已在真实启动周期中使用。
- `gimbal-joystick` 已有独立“云台摄像”桌面入口、实时画面、双轴摇杆、手掌跟踪/回中位/停止状态与退出。Qt 同一摄像头帧交给检测进程，不开第二套摄像头采集。2026-09-30 已获板屏现场反馈，最新边界见 [当前交接](../HANDOFF.md)。

### 存在代码但尚未现场验收

- Wi-Fi 相关最终视觉位置与完整触摸交互不以远程截图替代，仍需直接在板屏验收。

### 规划中/未实现

- 人物检测框、人物目标选择和整合语音/视觉任务的最终 HMI 尚未实现；已有“云台摄像”原型是后续复用入口。

## 系统 Wi-Fi

### 已确认实现

- ConnMan 是板端 Wi-Fi 管理器；Settings 保留 AWifi 的扫描列表与屏幕键盘。
- `ConnmanWifiController` 已用于读取连接状态、SSID、信号强度，并通过 ConnMan Agent 提交密码与调用连接。
- SystemUI 已有全局 Wi-Fi 状态层；Settings、SystemUI、aivoice 的相关 AArch64 构建、部署与冒烟测试均已完成。

### 存在代码但尚未现场验收

- 用户已在板屏连接新热点并确认重启后自动回连。右上角跨页面状态、真实列表及错误密码提示等完整清单未因此全部判为通过。
- 后续切换热点仍会中断 SSH，应在板屏操作并重新确认 DHCP 地址。

### 规划中/未实现

- 蓝牙不在当前范围内。

## MQTT

### 已确认实现

- Ubuntu VM 上的 Mosquitto Broker 与板端 MQTT pub/sub 已完成基础连通验证。

### 存在代码但尚未现场验收

- 无；当前资料没有可供验收的 MQTT 业务实现记录。

### 规划中/未实现

- `apps/mqtt-cloud` 是未来 MQTT/云端子项目入口；业务客户端、Topic/schema、断线重连、语音工具适配与 Qt 状态呈现均未实现。

## UART、STM32 与 Vision

### 已确认实现

- STM32F103C8T6 USART1 固件和 RK3568 UART9 M1 `/dev/ttyS9` 已完成 115200、8N1、无流控的现场连通；UART9 boot 持久化并经热重启、断电冷启动验证。
- ASCII `PING`/`PONG`、PC13 `LED ON`/`LED OFF`、`LED?` 状态回读及实物亮灭已有记录；二进制 CRC 仍只是草案。见 [HANDOFF](../HANDOFF.md)、[STM32 README](../stm32/README.md) 与 [UART 文档](uart-protocol-draft.md)。
- UVC 摄像头已完成 USB 枚举、1080p MJPEG/640×480 YUYV 取流、样帧与屏幕预览，证据在 `local/uvc-acceptance-20260928/`。
- STM32 已支持 PAN/TILT/TRK、双轴 PWM、限幅与 2 秒失联停止；手掌跟踪原型已部署。最新固件停止后保留最后输出脉宽，重启后 `TRK POS?` 为未知，显式回中位后才允许跟踪；参数与构建记录见 `apps/qt-ui/gimbal-joystick/README.md`、`local/gimbal-resume-fix-20260930.md`。
- 视觉模型为 MediaPipe 来源的 `palm_detection_lite.tflite`，通过 TFLite Runtime 在 CPU 推理；仅输出手掌位置与置信度，不识别人物或手势。现有代码没有配置 RKNN/NPU。

### 已现场使用、仍待量化的部分

- 摄像头、双轴 MG90S 与外部供电已用于实验；Pan 500–2500 µs、Tilt 750–2250 µs 有动作观察记录。供电电压/电流、负载余量、实际机械角度与机械延迟未测，不能把供应商参数或 PWM 回读当作实测轴角。
- 手掌跟踪最新反馈为“效果还可以，后面可以继续优化”，有启动及延迟反馈修复记录，仍未达到精确同步跟随或整机长期稳定性验收。

### 规划中/未实现

- Person 检测/目标选择、人物跟踪、RKNN 性能优化和语音启动/停止跟踪尚未实现。下一步先在现有预览中完成人物检测，再复用现有反馈控制。
- Qt 云台 worker 在整个应用运行期持有 UART9 文件锁；语音 PC13 或独立云台事务会返回 busy。语音启停跟踪需要受控的应用入口协调串口所有权、状态与回执，不能另开串口绕锁。
- 物理动作经过白名单、限幅和回执，LLM 不直接生成原始 UART 命令；阶段验收见 [模块推进路线](module-roadmap.md)。
