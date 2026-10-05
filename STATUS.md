# 项目状态

更新时间：2026-10-03（人物跟随基础测试正常，语音启停已部署并获实物有效反馈）

## 当前定位

RK3568 + AI 语音/视觉 + STM32 双轴云台的桌面智能视觉交互终端。当前已完成 UVC 取流、Qt 实时预览、人物检测/选择与双轴人物跟随基础实物验收；语音启动/停止 Person 跟踪已部署，真实录音联动待验收。阶段顺序和验收标准见 `ROADMAP.md` 与 `docs/module-roadmap.md`。

## 当前阶段摘要

2026-10-03 更新：CPU Person 检测、选框与双轴跟随已部署并获用户“测试完了，正常”反馈。
退出后 PAN/TILT/TRK OFF、摄像头及应用/UART 锁释放核对通过；记录 `local/person-follow-20261003/REPORT.md`。
语音启停已获授权部署，用户反馈“测试完毕，有效果”；日志确认语音开始 active、停止 off 均 accepted=True。退出后应用/worker 无进程，摄像头及应用/UART 锁释放，语音 idle。记录 `local/voice-tracking-20261003/REPORT.md`。联网/离线分项、多人交叉与长期稳定性仍未单独验收。

| 模块 | 当前结论 | 证据与边界 |
| --- | --- | --- |
| 联网语音 / PC13 | MiMo ASR、LLM、TTS 和灯控已现场验证 | `apps/voice/`、语音任务历史；普通对话使用流式路径，时间/天气走工具路径 |
| 离线固定语音 | 可用于阶段展示，仍有偶发拒识 | 语音任务 2026-09-26 记录：Wi-Fi 连着但无互联网时，4 轮灯控回读完成约 0.6–0.8 秒；1 轮未匹配未动作，联网恢复后的普通对话完成。该场景未出现长超时，不代表所有网络故障已覆盖 |
| UVC 摄像头 | 已到货、取流和板屏临时预览已验收 | `local/uvc-acceptance-20260928/`：1080p MJPEG 约 29.988 FPS、640×480 YUYV 约 29.994 FPS；USB 描述符的 500 mA 不是实测电流 |
| 双轴云台 / Qt | 舵机控制、预览、启停、退出及受限手掌跟踪已部署并获目视反馈 | `apps/qt-ui/gimbal-joystick/README.md`、`local/gimbal-resume-fix-20260930.md`；最新版反馈“效果还可以，后面可以继续优化” |
| 人物检测 / 跟随 | CPU TFLite Person 检测、选框与双轴跟随已部署，用户基础测试正常 | `local/person-follow-20261003/REPORT.md`；退出停止/释放通过，RKNN/NPU 未接入 |
| 语音人物跟踪 / 唤醒词 | 固定语音路由与本地控制入口已部署；语音 idle 与实际 STOP OFF 通过；唤醒词未接入 | `local/voice-tracking-20261003/REPORT.md`；真实录音/ASR/云台联动待验收 |

## 已完成

- [x] Ubuntu VM 与 Linux 5.10 SDK 环境搭建
- [x] AArch64 交叉编译与板端 Hello World 验证
- [x] Buildroot 5.10 系统烧录、串口登录和 MIPI 屏验证
- [x] Wi-Fi 自动连接与 VM/开发板网络互通
- [x] Mosquitto Broker 和板端 MQTT pub/sub 验证
- [x] ALSA 麦克风录音与扬声器播放
- [x] 百度 ASR 历史接入（当前主链已切换为 MiMo）
- [x] MiMo/GLM LLM 适配层
- [x] 火山引擎 TTS 历史接入（当前主链已切换为 MiMo）
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
- [x] STM32F103C8T6 独立 USART1 固件编译、ST-Link 下载和 PC13 LED 实物验收；原最小闪烁工程保留
- [x] RK3568 UART9 M1 候选镜像持久化写入 boot 分区，整分区写后回读、热重启及实际断电冷启动 SHA256 均匹配
- [x] 冷启动后 `/dev/ttyS9` 自动出现，`PING → PONG` 与 `LED? → LED=OFF` 通过；文本 LED 开关、回读和目视验收通过
- [x] 联网语音控制 STM32 PC13：明确开/关指令经 MiMo ASR、严格白名单、`OK` 与 `LED?` 回读验证，用户已目视确认亮灭
- [x] 用户在板屏连接新热点，并确认重启后自动回连（仅此部分已现场确认，不代表 Wi-Fi 全清单通过）
- [x] 离线固定语音控制 STM32 PC13 达到阶段性可用；断开 Wi-Fi 和 Wi-Fi 在线但无互联网的短测已有快速降级结果，仍有偶发拒识，未通过完整稳定性验收
- [x] UVC 摄像头 USB Host 枚举、1080p MJPEG / 640×480 YUYV 取流、有效样帧与板屏临时预览验收（2026-09-28）
- [x] STM32 双轴 PWM 与 PAN/TILT/TRK 文本控制、限幅、斜坡和 2 秒失联停止已实现；Qt“云台摄像”在板屏第二页有独立入口
- [x] Qt 同帧预览与 TFLite 手掌检测、双轴跟踪、人工停止和退出已现场使用；2026-09-30 修复重新启动跳回中位及延迟反馈过冲，最新版获用户“效果还可以”反馈

## 待验证

- [x] 将最新语音链路代码同步到开发板
- [ ] 使用 Qt 诊断页采集真实首句播放延迟和完整回答耗时
- [ ] 进行短周期多轮对话，确认录音不再出现恒定直流锁死
- [ ] 验证 Function Calling 与流式模式的降级逻辑
- [x] 由用户在 Qt 界面完成一轮真实“录音→ASR→MiMo→显示/TTS”验证
- [x] 整机重启后验证语音服务自启动及桌面图标启动流程
- [x] 在板屏选择新热点并完成重启后自动回连；切网后 IP 仍须重新确认。错误密码提示、跨应用状态等清单项尚未据此判为通过
- [ ] 离线固定语音 PC13 的拒识率与不同网络故障下的降级行为继续记录；已通过的短测无需反复重做
- [ ] 云台真实机械角度、供电电压/负载余量与长期表现未量化；当前脉宽边界与运行记录继续保留，不据此退回“硬件未到货”阶段
- [ ] 手掌跟踪仍有延迟和优化空间，未达到精确同步跟随；旧计时数据不代表修复后最终性能基线
- [x] Person 检测框、目标选择与双轴人物跟随已部署并获基础测试正常反馈，退出收尾通过（2026-10-03）
- [ ] 语音启动/停止人物跟踪开发验证中，尚未部署；RKNN 视模型兼容性和实测收益推进
- [ ] 中文唤醒词待板端识别验证与待机监听接入，按键入口保留

## 已知问题

- `apps/voice/config/config.py` 内嵌真实凭据，已被 Git 忽略，但仍必须迁移并轮换。
- Qt 应用当前采用轻触开始、再次轻触结束的按键模式，唤醒词尚未接入该 UI 流程。
- `wake/porcupine.py` 仍有历史硬编码问题。
- GLM API 当前不可用；板端使用 MiMo，部署时不得覆盖板端本地配置。
- 普通对话已使用流式路径，显式时间/天气意图走工具路径；真实首句延迟与完整回答耗时仍需进一步记录。
- 处理阶段暂不支持强制取消；录音阶段取消和下一轮恢复已验证。
- 历史语音运行基线约 2.79 GiB 可用内存；云台退出后的单次快照约 3191 MiB 可用。两者来自不同运行场景，不能作为当前实时值。
- 开发板与 VM 地址由 DHCP 分配，历史 IP 不能当作固定配置。
- 当前 UART 仅实现已验证的 ASCII 文本命令；二进制 CRC 协议仍为草案。UART9 boot 回退脚本已准备并做离线模拟/物理只读预检，但未执行实体回退写入。
- 厂商 `AWifi` 密码连接模板存在 `#[service_…]` 缺陷；当前只保留其扫描模型，连接改由 ConnMan D-Bus Agent 完成。用户已确认新热点连接及重启自动回连；错误密码提示等其他板屏细项未重新核实，远程不盲切当前 SSH 网络。
- 约 3.72 GiB 总内存是 4 GB 级板端实测，不是 8 GB；不规划本地大语言模型。摄像头、云台和外部供电已用于现场实验，实际电流、电压与角度未测。
- “云台摄像”工作进程在应用运行时独占 UART9 文件锁；语音 PC13 和独立云台 Action 此时会收到 busy。语音控制跟踪需要通过应用控制入口协调串口所有权，不能另开串口绕过锁。
- 仓库仍有多窗口的未提交修改，`stm32/`、`apps/qt-ui/gimbal-joystick/` 等尚未加入 Git 跟踪；本轮未提交或推送。

## 当前基线

- Windows 仓库：`D:\AProject\rk3568-ai-terminal`
- 语音开发副本：`D:\AProject\rk3568-ai-terminal\apps\voice`
- 板端部署目录：`/root/AI_voice`
- Ubuntu VM/SDK：`D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`（外部保留，不纳入 Git）
- 厂商资料：`D:\RK3568`（只读）
- 当前全局交接：`HANDOFF.md`；下一任务范围：`NEXT_TASK.md`；STM32 / 镜像基础记录：`stm32/README.md`、`docs/uart-protocol-draft.md`
- 最新云台记录：`apps/qt-ui/gimbal-joystick/README.md`、`local/gimbal-resume-fix-20260930.md`；最新应用 SHA256 为 `22ff21ba2c766bdfb726351268995282d936d86d1bc74f2f732d53db5b19c4aa`，详见交接
- Codex 保存的项目入口目前为父目录 `D:\AProject`；每个任务须明确进入上述真实仓库。旧语音窗口工作目录仍显示迁移前副本，不应依赖它定位源码
