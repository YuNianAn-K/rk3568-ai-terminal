# RK3568 AI 语音终端阶段整理

更新时间：2026-08-24

## 项目定位

目标是让正点原子 ATK-DLRK3568 开发板脱离电脑命令行，在板端完成按键录音、ASR、AI 对话/工具调用、文字显示和 TTS 播放，并逐步发展为可执行真实设备命令的 AI 终端。

## 本阶段已经完成

### 语音链路

- 梳理并审查了按键、录音、ASR、LLM、TTS、播放及下一轮恢复链路。
- 修复了 ASR 异常恢复、录音自动收尾、临时文件清理和播放超时等稳定性问题。
- 使用 16 kHz 统一音频输入输出，规避 RK817 采样率切换后录音锁死。
- 建立无 TTY 语音服务，支持 `status/start/stop/cancel`、单轮互斥和客户端重连。
- Qt 通过 `QLocalSocket` 连接 `/tmp/ai-voice.sock`，显示真实状态、ASR 文本和流式回答。
- 用户已完成多轮真实语音测试，异常后可继续下一轮。

### Qt 应用

- 新增独立 `aivoice` Qt Quick 应用和桌面图标，没有修改 PCBA。
- UI 采用简约黑白风格，包含语音状态、对话区域和隐藏诊断页。
- 应用已完成 AArch64 交叉编译、板端部署、SystemUI 生命周期接入和真实启动验证。
- 修复 Qt 退出时 Socket 信号问题以及真实对话文本显示问题。

### 可观测性与性能

- 增加统一 `[VOICE]` 阶段日志、服务资源快照和 Qt 诊断页面。
- 一次已记录样本为：麦克风打开 358 ms、录音收尾 117 ms、ASR 1351 ms、LLM 首响应约 8023 ms、TTS 1095 ms、播放 5058 ms、端到端 19211 ms。
- 该样本的最大等待来自 LLM 首响应；后续已做过一轮优化，用户主观确认明显改善，但本次对话没有保存优化后的完整诊断数值，不能虚构新基线。
- 内存基线：总内存约 3.72 GiB、可用约 2.79 GiB；语音服务约 119 MiB，Qt 应用约 138 MiB，当前容量充足。

## 已知限制

- GLM API 不可用，板端使用 MiMo；部署不能覆盖板端本地凭据配置。
- `apps/voice/config/config.py` 仍含历史明文凭据，该文件已被 Git 忽略；仍须迁移到环境变量或未提交的本地配置并轮换。
- 工具 schema 目前影响普通聊天流式路径，真正的“语音执行命令”还需要工具注册、权限、确认、执行结果和审计层。
- 处理阶段还不支持可靠强制取消；录音阶段取消与下一轮恢复已验证。
- 唤醒词尚未接入当前 Qt 交互，按键仍是可靠入口。
- 用户明确不进行 100 轮和 24 小时长测；后续采用短周期、可观察验证。

## Wi-Fi 系统集成结果

用户最终要求是手机式系统体验：右上角全局显示当前 SSID/信号，连接入口沿用系统“设置→无线局域网”，不在 aivoice 内另做网络面板。

已完成：

- 现场确认板端由 ConnMan 管理 Wi-Fi，厂商 Settings 的 AWifi 扫描模型能正确显示真实 SSID、加密类型和信号。
- 反汇编定位厂商密码连接失败根因：其 ConnMan 配置模板首行是 `#[service_%1]`，服务节被注释，密码不会生效；AWifi 还会管理 `connmanctl monitor`，不适合作为常驻全局状态源。
- 新增 `ConnmanWifiController`，通过系统 D-Bus 读取连接/SSID/强度，并注册 ConnMan Agent 安全提交密码、异步调用服务 Connect。
- SystemUI 新增顶层 `WifiStatusOverlay`，右上角显示真实 SSID、三级信号或“Wi-Fi 未连接”。
- Settings 保留原 AWifi 扫描和虚拟键盘，只将选择网络、密码提交、错误/成功提示切换到 ConnMan D-Bus 控制器。
- aivoice 的错误 Wi-Fi 面板已从构建与 QML 中撤销，VoiceBridge 和 Python 语音服务未修改。
- 三个 AArch64 UI 二进制已经部署；板端状态测试得到当前 SSID、强度 68，Connect 冒烟测试成功，aivoice 连接语音 Socket 正常。

尚待用户在板屏选择一个可控的新热点完成真实密码切换；该操作会中断 SSH，之后必须重新确认 DHCP 地址。Weston 截图协议未授权，最终视觉位置也需直接看板屏确认。

## 2026-08-30 迁移与 Git 补记

- 项目已迁移到单一仓库 `D:\AProject\rk3568-ai-terminal`，Git 主分支为 `main`。
- Python 语音、Qt 应用、MQTT 入口、系统 Qt 改动和外壳模型分别归入 `apps/voice`、`apps/qt-ui`、`apps/mqtt-cloud`、`platform/qt-system` 与 `hardware/enclosure`。
- 原 `app/lab` 目录联接已移除，不再作为项目入口。
- 41.1 GB Ubuntu VM/SDK 仍在 `D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`，未移动、复制或纳入 Git。
- 本地访问脚本迁入 `local/` 并被 Git 忽略；历史凭据配置、缓存与 Qt 构建产物也已通过 `.gitignore` 排除。
- `platform/qt-system/qsetting` 的厂商快照已展平进入主仓库；原提交 `9417cc6` 的 Git 元数据保存在已忽略的 `local/embedded-git/qsetting.git`，需要时可恢复。
- AIwork 根目录的 6 个重复外壳入口经 SHA-256 确认与仓库文件一致后清理，另一个不同版本 STL 保存在 `hardware/enclosure/archive`。

## 新任务衔接原则

- 长期事实写入 `STATUS.md`，路线写入 `ROADMAP.md`。
- 当前唯一任务、已查证事实和下一步写入根目录 `NEXT_TASK.md`。
- 新任务只需读取 `AGENTS.md`、四个项目入口文档和目标源码，不需要读取完整聊天历史。
- 每完成一个可验证里程碑，就更新 `STATUS.md` 和 `NEXT_TASK.md`；代码稳定点再做 Git 提交和标签。
