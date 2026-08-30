# 项目状态

更新时间：2026-08-30

## 已完成

- [x] Ubuntu VM 与 Linux 5.10 SDK 环境搭建
- [x] AArch64 交叉编译与板端 Hello World 验证
- [x] Buildroot 5.10 系统烧录、串口登录和 MIPI 屏验证
- [x] Wi-Fi 自动连接与 VM/开发板网络互通
- [x] Mosquitto Broker 和板端 MQTT pub/sub 验证
- [x] ALSA 麦克风录音与扬声器播放
- [x] 百度 ASR 接入
- [x] MiMo/GLM LLM 适配层
- [x] 火山引擎 TTS 接入
- [x] 录音、ASR、LLM、TTS、播放全链路
- [x] RK817 24 kHz/16 kHz 切换导致的录音锁死修复
- [x] 时间、天气 Function Calling
- [x] 流式 LLM 分句、TTS 消费队列代码
- [x] 语音稳定性修复部署：ASR 异常恢复、录音自动收尾、临时文件清理、播放超时
- [x] 板端短周期验证：快速双击自动收尾、连续两轮录音可恢复、无临时 WAV/子进程残留
- [x] 新增 `aivoice` Qt Quick 应用：简约黑白界面、独立桌面图标、SystemUI 生命周期接入
- [x] Qt 应用交叉编译和板端启动验证：QML 静态检查通过、AArch64 运行无解析错误
- [x] Qt/Python 语音接入：`QLocalSocket` 连接 `/tmp/ai-voice.sock`，显示真实状态、ASR 文本和流式回答
- [x] 无 TTY 语音服务接入：支持 `status/start/stop/cancel`、单轮互斥、客户端重连和异常回到待机
- [x] 正式板端部署与短周期验证：8 项单元测试通过，两轮开始/取消后可继续，服务重启后 Qt 自动重连
- [x] 用户真实语音验证：连续 4 轮 ASR、MiMo/工具调用、TTS 均成功并回到待机
- [x] 时间与 Qt 退出修复：工具显式使用 UTC+8，`VoiceBridge` 关闭 Socket 前断开成员信号
- [x] 语音可观测性接入：统一 `[VOICE]` 阶段耗时日志、服务资源快照和 Qt 隐藏诊断页
- [x] 当前启动周期验证：Buildroot `rcS` 自动执行 `S99ai-voice`，桌面图标、配置条目和应用启动正常
- [x] 正式运行内存基线：3.72 GiB 总内存、约 2.79 GiB 可用；语音服务约 119 MiB、Qt 应用约 138 MiB
- [x] 系统级 Wi-Fi 状态：SystemUI 右上角常驻显示真实 SSID、连接状态和三级信号强度
- [x] 系统 Settings Wi-Fi 完善：保留厂商 AWifi 扫描/SSID 列表和屏幕键盘，ConnMan D-Bus Agent 接管密码提交与连接
- [x] 撤销 aivoice 应用内 Wi-Fi 面板：构建与 QML 中不再包含 WifiPanel/WifiBridge，语音桥保持独立
- [x] Wi-Fi 版本交叉编译与板端部署：Settings、SystemUI、aivoice 和冒烟测试均通过，旧二进制已集中备份
- [x] OpenSCAD 保护底座和防尘盖模型
- [x] Windows 项目迁移：语音、Qt、MQTT、系统适配和外壳统一整理到 `D:\AProject\rk3568-ai-terminal`
- [x] Git 仓库初始化为 `main`，大型 VM/SDK、历史凭据、本地脚本和构建产物均排除在版本库外

## 待验证

- [x] 将最新语音链路代码同步到开发板
- [ ] 使用 Qt 诊断页采集真实首句播放延迟和完整回答耗时
- [ ] 进行短周期多轮对话，确认录音不再出现恒定直流锁死
- [ ] 验证 Function Calling 与流式模式的降级逻辑
- [x] 由用户在 Qt 界面完成一轮真实“录音→ASR→MiMo→显示/TTS”验证
- [x] 整机重启后验证语音服务自启动及桌面图标启动流程
- [ ] 在板端系统“设置→无线局域网”选择一个可控的新热点，完成一次真实密码连接与回连验收（切网后需重新确认 IP）

## 已知问题

- `apps/voice/config/config.py` 内嵌真实凭据，已被 Git 忽略，但仍必须迁移并轮换。
- Qt 应用当前采用轻触开始、再次轻触结束的按键模式，唤醒词尚未接入该 UI 流程。
- `wake/porcupine.py` 仍有历史硬编码问题。
- GLM API 当前不可用；板端使用 MiMo，部署时不得覆盖板端本地配置。
- 工具 schema 当前始终启用，普通对话仍走非流式 Function Calling 路径。
- 处理阶段暂不支持强制取消；录音阶段取消和下一轮恢复已验证。
- 开发板未配置 swap，但当前仍有约 2.79 GiB 可用内存。
- 开发板与 VM 地址由 DHCP 分配，历史 IP 不能当作固定配置。
- 厂商 `AWifi` 密码连接模板存在 `#[service_…]` 缺陷；当前只保留其扫描模型，连接改由 ConnMan D-Bus Agent 完成。新热点真实密码切换仍需在板屏验收，远程不盲切当前 SSH 网络。

## 当前基线

- Windows 仓库：`D:\AProject\rk3568-ai-terminal`
- 语音开发副本：`D:\AProject\rk3568-ai-terminal\apps\voice`
- 板端部署目录：`/root/AI_voice`
- Ubuntu VM/SDK：`D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`（外部保留，不纳入 Git）
- 厂商资料：`D:\RK3568`（只读）
- 当前 Windows 代码语法检查：通过
