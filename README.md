# RK3568 智能视觉交互终端

这是 RK3568 项目的统一 Git 仓库。语音、Qt、MQTT、系统适配和外壳模型都在同一仓库内按子项目分类；大型 Ubuntu VM/SDK 和厂商资料仍保留在外部，不复制进仓库。

## 项目目标

基于正点原子 ATK-DLRK3568 与 STM32F103C8T6，构建桌面智能视觉交互终端：

1. 麦克风录音与按键触发，后续接入中文唤醒词
2. 中文语音识别
3. 大模型对话与工具调用
4. 语音合成和板载扬声器播放
5. 离线固定指令与受控本地设备控制
6. 摄像头人物检测、STM32 双轴云台跟踪，以及语音启动/停止跟踪

目前已有实时预览和手掌跟踪原型，人物检测与语音跟踪闭环是下一阶段目标。MQTT 保留已有连通成果，业务扩展不阻挡主线；板端约为 4 GB 内存级别，不部署本地大语言模型。

## 目录入口

| 目录 | 用途 |
| --- | --- |
| `apps/voice` | Python 语音服务、ASR、LLM、TTS、音频与测试 |
| `apps/qt-ui` | `aivoice` 语音界面、`gimbal-joystick` 摄像头/手掌跟踪应用及构建集成 |
| `apps/mqtt-cloud` | MQTT/云端子项目入口与后续实现 |
| `platform/qt-system` | Settings、SystemUI、ConnMan 等厂商 Qt 系统改动副本 |
| `hardware/enclosure` | OpenSCAD 源文件、STL、预览及旧版本归档 |
| `stm32` | STM32F103C8T6 的 PC13 基线、USART1 通信、双轴 PWM/跟踪固件与验收说明 |
| `tools/uart-smoke.py` | RK3568 `/dev/ttyS9` 的单轮 `PING` / `LED?` 文本协议检查 |
| `docs` | 项目历史、阶段总结和部署资料 |
| `local` | 本机访问脚本和机器相关配置，不进入 Git |

外部环境：

- Ubuntu VM/SDK：`D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`
- 厂商资料：`D:\RK3568`（只读）
- 板端语音部署目录：`/root/AI_voice`

## 当前状态

- 开发板：Buildroot 2021.11、Linux 5.10，5.5 寸 MIPI DSI 屏已点亮。
- 开发环境：Ubuntu VM、Linux 5.10 SDK 和 AArch64 交叉编译工具链已跑通。
- 网络：开发板 Wi-Fi 自动连接已通过，VM 上 Mosquitto Broker 与板端客户端通信已通过。
- 语音链路：录音 → MiMo ASR → MiMo LLM → MiMo TTS → ALSA 播放已在板子上跑通；联网及离线固定语音 PC13 控制已有现场结果。
- 音频稳定性：已通过播放前重采样到 16 kHz 修复 RK817 播放后录音锁死问题。
- 智能能力：已实现时间、天气工具调用。
- 流式响应：代码与板端部署已完成，仍需测量真实首句延迟和完整回答耗时。
- STM32/UART：USART1 固件已编译、烧录并完成 PC13 LED 实物验收；RK3568 UART9 M1 boot 镜像已持久化，热重启与断电冷启动后的 `/dev/ttyS9` 和基础收发均验证通过。原始 boot 备份、候选镜像及专用回退脚本保留在仓库外，详见 [STM32 说明](stm32/README.md) 与 [阶段交接](HANDOFF.md)。
- 视觉云台：UVC 取流已验收；独立“云台摄像”Qt 应用已部署，支持实时画面、双轴手动控制及受限手掌跟踪。模型是 TFLite 手掌检测，现有代码使用 CPU；人物检测/RKNN 尚未实现。最新实物反馈与版本见 [云台说明](apps/qt-ui/gimbal-joystick/README.md) 和 [STATUS.md](STATUS.md)。

详细进度见 [STATUS.md](STATUS.md)，后续路线见 [ROADMAP.md](ROADMAP.md)。

## 常用验证

```powershell
# [Windows] 仅做语法编译检查，不调用外部 API
py -m compileall -q D:\AProject\rk3568-ai-terminal\apps\voice
```

```bash
# [开发板] 串口终端运行
cd /root/AI_voice
python3 main.py
```

开发板和 VM 使用 DHCP，操作前先确认当前 IP，不依赖历史记录中的旧地址。

## 安全提醒

现有 `apps/voice/config/config.py` 中仍有历史凭据，该文件已被 `.gitignore` 排除。不要提交、分享或复制其内容；下一阶段应先轮换凭据，并改为从环境变量或未提交的本地配置读取。

当前长期事实以 `STATUS.md` 为准，后续路线以 `ROADMAP.md` 为准，当前交接点以 `NEXT_TASK.md` 为准。
