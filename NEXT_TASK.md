# 下一任务入口

更新时间：2026-10-14

## 当前真正的下一步

**先完成 MQTT 一次真实只读联调，再继续结构试装和交互体验收尾；不重复开发唤醒词、NPU 或 Wi-Fi 修复。**

1. 窗口“RK3568｜MQTT 云端接入与 MQTTX”，沿用当前模型、中等强度：代理已在 `/opt/rk3568-mqtt-status-20261013/`，专用账号/主题 ACL 已配好。使用前现场确认地址、ping/可信 SSH、CA/时间及凭据；运行独立代理，手机 `get_status` 与真实 `/proc` 对照，核对新账号登录、权限隔离、断线/过期。无自启动，不加运动或视频，不改 VPN/计费。入口 `apps/mqtt-cloud/client/README.md`。
2. 窗口“RK3568｜双层结构与 OpenSCAD（接续）”，中等强度：V2 试装顶板已生成，先确认独立底板/立柱匹配及风扇、插头、FPC 余量。`local/hardware-dual-layer-20261014/top-plate-v2-print/README.md` 为最新试装说明，不套用旧并排加工图，不默认适配原屏幕铜柱。
3. 语音窗口中等强度、视觉窗口复杂分析时 High：LLM 已为 V2.6 Flash、正式视觉已为 v8 INT8 NPU。分别处理真实对话长等待和低头漏检/最终停跟，先复用日志/失败采样，必要时才做一次针对性短测；不自动训练或换 YOLO26。
4. UI 窗口中等强度：统一入口和状态提示仍待实施，在现有页面增量整合，不重写整套系统。总控负责一轮整机验收与交付材料。

第一版边界：开机/语音入口、受控开始与停止跟随、离线基本控制、明确状态、可靠固定及可恢复版本。多人重识别、寻找物体、新传感器、视频云服务和远程运动不阻挡交付。UART/boot/固件不因应用收尾重刷，不能让 LLM 直接生成 UART。

部署与回退哈希见 `HANDOFF.md` 顶部；源码提交不替代板端恢复。云端账号密码、权重、采样、部署备份及打印产物保持在忽略目录，不能为“工作区干净”误提交。

## 历史任务入口（2026-10-03，已由上方覆盖）

**语音开始/停止人物跟随已部署，用户反馈“测试完毕，有效果”；下一步建议完成稳定性及联网/离线分项验收，尚未执行。** 日志确认一轮语音开始 active、停止 off 均 accepted=True；退出后应用/worker 无进程、摄像头及应用/UART 锁释放，语音 idle。完整备份 20 个文件校验通过，记录见 `local/voice-tracking-20261003/REPORT.md`。多人交叉和长时间稳定性未单独验收。

本轮用户已批准开发：云台应用增加受控本地 Socket，语音的明确固定指令通过应用启停，不另开 UART。开始需板屏开启人物检测并选择新鲜目标、相机/控制可用、位置已初始化；多人未选目标提示先选框，不自动回中位。停止等双轴 OFF 回执，重复/过期/错误指令不触发新动作。

云台窗口失焦会停止检测与跟随，因此在云台页复用已有语音录音服务；按键录音入口保留，中文唤醒词不属于本轮。候选清单、部署前哈希、回退范围及验证记录见 `local/voice-tracking-20261003/REPORT.md`；正式部署及实物动作测试按用户授权执行。

窗口：当前视觉云台窗口完成接口，现有语音窗口可续接语音路由；本轮不新建窗口、不发送跨窗口消息。建议沿用项目配置 `gpt-6.1-sol`、中等思考强度。仓库 `D:\AProject\rk3568-ai-terminal` 有多窗口改动，保留现有代码，不提交或推送。

## 当前交接点

正式板端人物跟随应用 SHA256 `0f8c055fe43a1f8648cfae17a4f9978ae07121ff7d05aff0ab672fa18e4c67c2`，worker `6c48671194d812b3f4609431a9c442a8e3dcfca312bf5d6c131349f59c6640c2`；固件未改。检测版回退目录 `/opt/ui/gimbal-joystick.pre-person-follow-20261003/`，17 个原文件核对通过。使用前确认板端当前地址并 ping，UART 查询先核对应用与文件锁占用；不重复写 boot、另开摄像头或绕过锁。

供电、真实机械角度、长期表现仍未量化；当前 CPU 推理不等于 RKNN/NPU 已启用。

## 联网语音控制阶段（历史已完成）

联网的“打开指示灯”“关闭指示灯”已通过 MiMo ASR、严格白名单及 `OK`/ `LED?` 回读控制 PC13；用户目视确认先亮后灭。2026-09-26 离线短测覆盖断开 Wi-Fi 和 Wi-Fi 在线但无互联网，后者 4 轮灯控约 0.6–0.8 秒完成回读，另有 1 轮未匹配未动作；恢复联网后可以对话。仍有偶发拒识，完整稳定性未验收，已通过场景不必反复重做。

当前协议仍是 115200、8N1、无流控的 ASCII 文本协议；二进制 CRC 协议仅在 `docs/uart-protocol-draft.md` 中规划，未实现。调试控制台 `ttyFIQ0` 不参与业务通信。不得未经确认并联 RK3568 与 ST-Link 的 3V3 供电，亦不得把 5V 接到 UART 信号线。

## 并行遗留事项

用户已在板屏连接新热点并确认重启后自动回连；错误密码提示和跨页面状态等其余 Wi-Fi 清单项未一并判为通过。历史 IP 不能作为固定地址。Qt、语音和 UI 的其他未提交修改由各自工作窗口维护，下一任务不要覆盖或回退。

中文唤醒词“小爱同学”已讨论，停在板端诊断录音准备，尚未接入待机监听。语音工作与人物检测独立推进；恢复语音任务时明确进入真实仓库，旧语音窗口 cwd 仍指向迁移前副本。Git 基线整理属于总控收尾，未获要求不自动提交或推送。

## 历史 Wi-Fi 交接（2026-08-30，保留原始记录）

以下保留上一阶段原文，仅供查证，不是当前任务指令。新任务只需读取上面的当前入口；历史细节按需查阅。

### 历史新任务快速交接

更新时间：2026-08-30

### 历史目标

系统级 Wi-Fi 功能已经实现并部署。下一步只做板屏真实交互验收：

1. 确认任意应用右上角都能看到当前 SSID 与 Wi-Fi 信号强度。
2. 在系统“设置→无线局域网”确认真实 SSID 列表和锁/信号图标。
3. 选择一个可控的新热点，用屏幕键盘输入密码并连接。
4. 验证错误密码提示、连接成功提示以及重启后的自动回连。
5. 切网会中断 SSH；操作后必须重新现场确认 VM 与开发板 DHCP 地址。

蓝牙不实现；Wi-Fi 不再放进 aivoice；不得改动现有语音链路。

### 历史已确认事实

- 本次现场确认 VM 为 `172.20.10.9`、开发板为 `172.20.10.10`；这些地址只代表本次会话，后续仍须重新确认。
- 板端由 ConnMan 管理 Wi-Fi，现有热点 `kk的iPhone` 在线。
- 厂商 Settings 页面使用 `AQuickPlugin 1.0` 的 `AWifi`，扫描、SSID 名称、信号和屏幕键盘可用。
- 厂商 `AWifi` 的密码连接线程包含 `#[service_%1]` 配置节错误，导致密码配置被注释；它还会管理 `connmanctl monitor`，不适合作为常驻系统状态源。
- 当前实现保留 AWifi 扫描模型，新增 `ConnmanWifiController` 通过系统 D-Bus 注册 ConnMan Agent 并调用服务 `Connect`。
- SystemUI 使用同一控制器只读获取连接、SSID 和强度，并以独立顶层窗口显示在右上角。
- aivoice 已从构建和 QML 中移除 `WifiPanel/WifiBridge`，`VoiceBridge` 未改动。

### 历史部署与验证

- `/opt/ui/systemui`：`04bbbda0793689552b6aa17aa1937bd4b9629446717287ad4d5892d7a4aab824`
- `/opt/ui/src/apps/settings`：`69ce6c87ced67566260245e9162d6575c824f63b25801a364f657d4a4d40c6a5`
- `/opt/ui/src/apps/aivoice`：`a0e2f5424f6f2838b2c0fb7d4496cecee49fa444f2ba04b7515b33bd95c3319a`
- 板端备份目录：`/opt/ui/.codex-backups/20260824-global-wifi/`
- VM 源码备份：`/home/alientek/rk3568_sdk/app/alientek/qt_demo/ui/.codex-backups/20260824-global-wifi/`
- AArch64 三项目编译、aivoice 生命周期测试和修改后 QML lint 均通过。
- 板端状态冒烟测试：`connected=true`，SSID UTF-8 为 `6b6be79a846950686f6e65`，强度 `68`。
- ConnMan Agent/Connect 对当前已连接服务冒烟测试成功，网络保持在线。
- 新 aivoice 实际启动无 QML/error 日志，`/tmp/ai-voice.sock` 为 `ESTAB`；随后已切回 Settings 页面。
- Weston 截图协议未授权，因此最终视觉位置需由板屏直接确认，不能用远程截图替代。

### 历史关键文件

- `platform/qt-system/wificommon/connmanwificontroller.h/.cpp`：ConnMan 状态和连接控制器。
- `platform/qt-system/systemui/WifiStatusOverlay.qml`：全局右上角 SSID/信号层。
- `platform/qt-system/settings/qwifi/`：厂商设置页上的选择、密码和连接交互。
- `apps/qt-ui/aivoice/main.cpp`、`main.qml`、`aivoice.pro`、`qml.qrc`：已撤销应用内 Wi-Fi。
- `STATUS.md`：长期项目状态。

### 历史安全边界

- Wi-Fi 密码不得进入命令行、日志、文档或提交；ConnMan Agent 使用后立即清空内存中的密码字符串。
- 不远程切换当前承载 SSH 的 Wi-Fi；真实新热点测试由板屏操作。
- 不实例化第二套 AWifi 常驻监控，避免互相终止 `connmanctl monitor`。
- 不修改语音服务、音频采样率和 `/tmp/ai-voice.sock` 协议。

### 历史任务第一条消息（不再作为当前入口）

> 请先读根目录 `AGENTS.md`、`README.md`、`STATUS.md`、`ROADMAP.md` 和 `NEXT_TASK.md`。先重新确认 VM/开发板 IP，再在板屏验收 SystemUI 右上角 Wi-Fi 状态和系统 Settings 密码连接；不实现蓝牙，不把 Wi-Fi 放回 aivoice，不影响语音链路。
