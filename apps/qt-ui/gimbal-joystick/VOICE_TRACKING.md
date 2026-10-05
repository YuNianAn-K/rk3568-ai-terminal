# 语音人物跟随开发版

2026-10-03：代码、模拟协议与隔离验证阶段；尚未安装到正式板端应用/语音服务。

## 板屏流程

1. 打开“云台摄像”；位置未知时显式回中位。
2. 开启“人物检测”，单人自动选框，多人点击框选择。
3. 点“说话控制云台”，说“开始跟踪人物”，再点“结束录音”。
4. 观察语音文字回执与云台状态；说“停止跟踪”使用同一录音按钮。

开始前检查窗口活动、相机、控制连接、初始化位置及 500 ms 内的新鲜选中目标。
语音不启动未知位置回中位、不替用户从多个框中选人。已有跟随时重复开始只回当前已 ARM 状态。
停止取消检测与跟随并等双轴 OFF；立即停止与退出仍可触控使用。
窗口隐藏/失焦会停止视觉跟随，所以录音复用现有 VoiceBridge 与语音服务，在云台页内进行。
中文唤醒词不在本版。已有语音服务处理阶段仍不支持强制取消，关闭云台页后开始请求会被拒绝。

## 控制接口

应用以 owner-only 本地 Socket `/tmp/gimbal-tracking.sock` 提供 JSON Lines，
每连接一个请求，最大 4096 字节，最多 4 个客户端；不接收原始 UART、模型坐标或 Shell。
Voice 服务 Socket `/tmp/ai-voice.sock` 的录音协议保持原样。

```json
{"version":1,"request_id":"0123456789abcdef0123456789abcdef","command":"START_TRACKING","target":"PERSON","issued_ms":123456789}
```

- `command` 仅为 `START_TRACKING` 或 `STOP_TRACKING`。
- `request_id` 为调用方生成的 32 位小写十六进制编号。
- `issued_ms` 是本机单调时钟毫秒；未来或超过 1500 ms 的请求拒绝。
- 保存最近 64 个编号，重复编号拒绝，不重复执行；并发开始返回 busy，停止可以取消未确认开始。
- 应用等待硬件证明最多 4 秒，Python 客户端总等待 5 秒，不自动重试。
- 开始回执 `accepted=true, code=active` 只在相同编号的 ARM 后返回；停止 `code=off` 等相同编号的双轴 OFF。
- 超时或客户端在开始确认前断开，撤销该开始请求并请求停止；UART 异常不伪造 OFF。
- 其他码：`select_target`、`position_unknown`、`camera_unavailable`、`inactive`、`busy`、`lost`、`controller_unavailable`、`cancelled`、`timeout`、`invalid`、`duplicate`。

worker 的本地 stdin 新增 `PERSON_START <request_id>` 和 `CONTROL_STOP <request_id>`，
只用于 UI/worker 回执关联，发送给 STM32 的 PAN/TILT/TRK 协议和固件不变。
原手掌模式和人物检测/控制参数保留。正式更新须配套应用与 worker；语音候选仅修改固定路由、离线语法及新增客户端。

## 验证边界

Windows 实际 QML 用模拟相机/语音数据检查按钮与目标拒绝；语音回归不调用外部 API。
Qt5 控制入口在开发板 /tmp 中使用不会打开 UART 的 fixture 检查回执关联和异常路径。
这不能替代真实录音、ASR、TTS、云台方向、目标丢失与停止/退出的实物验收。
