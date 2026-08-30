# 新任务快速交接

更新时间：2026-08-30

## 当前目标

系统级 Wi-Fi 功能已经实现并部署。下一步只做板屏真实交互验收：

1. 确认任意应用右上角都能看到当前 SSID 与 Wi-Fi 信号强度。
2. 在系统“设置→无线局域网”确认真实 SSID 列表和锁/信号图标。
3. 选择一个可控的新热点，用屏幕键盘输入密码并连接。
4. 验证错误密码提示、连接成功提示以及重启后的自动回连。
5. 切网会中断 SSH；操作后必须重新现场确认 VM 与开发板 DHCP 地址。

蓝牙不实现；Wi-Fi 不再放进 aivoice；不得改动现有语音链路。

## 已确认事实

- 本次现场确认 VM 为 `172.20.10.9`、开发板为 `172.20.10.10`；这些地址只代表本次会话，后续仍须重新确认。
- 板端由 ConnMan 管理 Wi-Fi，现有热点 `kk的iPhone` 在线。
- 厂商 Settings 页面使用 `AQuickPlugin 1.0` 的 `AWifi`，扫描、SSID 名称、信号和屏幕键盘可用。
- 厂商 `AWifi` 的密码连接线程包含 `#[service_%1]` 配置节错误，导致密码配置被注释；它还会管理 `connmanctl monitor`，不适合作为常驻系统状态源。
- 当前实现保留 AWifi 扫描模型，新增 `ConnmanWifiController` 通过系统 D-Bus 注册 ConnMan Agent 并调用服务 `Connect`。
- SystemUI 使用同一控制器只读获取连接、SSID 和强度，并以独立顶层窗口显示在右上角。
- aivoice 已从构建和 QML 中移除 `WifiPanel/WifiBridge`，`VoiceBridge` 未改动。

## 部署与验证

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

## 当前关键文件

- `platform/qt-system/wificommon/connmanwificontroller.h/.cpp`：ConnMan 状态和连接控制器。
- `platform/qt-system/systemui/WifiStatusOverlay.qml`：全局右上角 SSID/信号层。
- `platform/qt-system/settings/qwifi/`：厂商设置页上的选择、密码和连接交互。
- `apps/qt-ui/aivoice/main.cpp`、`main.qml`、`aivoice.pro`、`qml.qrc`：已撤销应用内 Wi-Fi。
- `STATUS.md`：长期项目状态。

## 安全边界

- Wi-Fi 密码不得进入命令行、日志、文档或提交；ConnMan Agent 使用后立即清空内存中的密码字符串。
- 不远程切换当前承载 SSH 的 Wi-Fi；真实新热点测试由板屏操作。
- 不实例化第二套 AWifi 常驻监控，避免互相终止 `connmanctl monitor`。
- 不修改语音服务、音频采样率和 `/tmp/ai-voice.sock` 协议。

## 新任务第一条消息

> 请先读根目录 `AGENTS.md`、`README.md`、`STATUS.md`、`ROADMAP.md` 和 `NEXT_TASK.md`。先重新确认 VM/开发板 IP，再在板屏验收 SystemUI 右上角 Wi-Fi 状态和系统 Settings 密码连接；不实现蓝牙，不把 Wi-Fi 放回 aivoice，不影响语音链路。
