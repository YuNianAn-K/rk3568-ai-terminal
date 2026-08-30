# RK3568 AI 语音终端

这是 RK3568 项目的统一 Git 仓库。语音、Qt、MQTT、系统适配和外壳模型都在同一仓库内按子项目分类；大型 Ubuntu VM/SDK 和厂商资料仍保留在外部，不复制进仓库。

## 项目目标

让正点原子 ATK-DLRK3568 开发板在只连接 Wi-Fi 的情况下独立完成：

1. 麦克风录音与唤醒/按键触发
2. 中文语音识别
3. 大模型对话与工具调用
4. 语音合成和板载扬声器播放
5. 后续扩展 MQTT、传感器和本地设备控制

## 目录入口

| 目录 | 用途 |
| --- | --- |
| `apps/voice` | Python 语音服务、ASR、LLM、TTS、音频与测试 |
| `apps/qt-ui` | `aivoice` Qt Quick 应用及构建集成补丁 |
| `apps/mqtt-cloud` | MQTT/云端子项目入口与后续实现 |
| `platform/qt-system` | Settings、SystemUI、ConnMan 等厂商 Qt 系统改动副本 |
| `hardware/enclosure` | OpenSCAD 源文件、STL、预览及旧版本归档 |
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
- 语音链路：录音 → 百度 ASR → LLM → 火山 TTS → ALSA 播放已在板子上跑通。
- 音频稳定性：已通过播放前重采样到 16 kHz 修复 RK817 播放后录音锁死问题。
- 智能能力：已实现时间、天气工具调用。
- 流式响应：代码已经完成，仍需重新部署到板子并测量首句延迟。

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
