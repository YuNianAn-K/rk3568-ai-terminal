# 模块接口与消息边界（规划）

更新时间：2026-09-05

## 定位与状态

本文定义未来模块间应遵循的抽象边界，不引入实现、端口、线程、依赖或部署变更。

- **已确认实现**：Voice 服务与 Qt aivoice 已通过 AF_UNIX Socket `/tmp/ai-voice.sock` 通信；现有命令为 `status`、`start`、`stop`、`cancel`。
- **存在代码但尚未现场验收**：System Wi-Fi 的最终板屏交互与新热点回连。
- **规划中/未实现**：下文的稳定消息信封、MQTT 工具网关、UART 适配器、STM32 设备服务和 Vision 事件接口。

## 共通消息原则

所有未来跨模块消息应满足：

| 字段 | 规则 |
| --- | --- |
| `version` | 协议版本，初始为 `1`；不兼容修改必须升级。 |
| `request_id` | 调用方生成的唯一标识，用于幂等、回执和审计关联。 |
| `source` | 发送模块，例如 `ui`、`voice`、`mqtt`、`uart`、`vision`。 |
| `type` | 明确事件或命令类型，禁止以自然语言作为控制协议。 |
| `timestamp_ms` | 发送时的 Unix 毫秒时间戳，仅用于观测，不作为唯一顺序依据。 |
| `payload` | 与 `type` 对应的结构化数据；不得包含 API Key、Wi-Fi 密码或原始令牌。 |

状态改变命令必须同时具备：可验证的目标标识、明确的参数、可关联的结果回执、超时语义和幂等策略。

## UI ↔ Voice

### 已确认实现

- Qt 通过本地 Socket 从 Voice 服务获取状态、识别文本、回答增量、回答结果、错误和诊断。
- Voice 服务当前接受单轮录音控制命令；处理阶段不承诺强制取消。

### 规划中/未实现

未来应把现有消息稳定为如下逻辑分类，而不是让 UI 了解 ASR、LLM 或 TTS 的内部细节：

| 方向 | 消息类型 | 目的 |
| --- | --- | --- |
| UI → Voice | `voice.round.start` / `voice.round.stop` / `voice.round.cancel` | 仅控制一次语音会话生命周期。 |
| Voice → UI | `voice.state` | 报告 `idle`、`recording`、`recognizing`、`thinking`、`replying`、`playing`、`error`。 |
| Voice → UI | `voice.transcript` / `voice.answer.delta` / `voice.answer.final` | 展示用户语音转写和回答，不承载控制命令。 |
| Voice → UI | `voice.diagnostics` | 仅提供经过脱敏的耗时、资源与连接状态。 |

## UI ↔ System Wi-Fi

### 已确认实现

- Settings 与 SystemUI 已从 ConnMan 控制器取得连接、SSID 与信号信息；密码连接由 ConnMan Agent 处理。

### 规划中/未实现

未来 UI 只消费稳定的只读状态对象，不直接持有 Wi-Fi 密码或调用底层 D-Bus：

```json
{
  "type": "network.wifi.state",
  "payload": {
    "connected": true,
    "ssid": "example-network",
    "strength": 0,
    "state": "online"
  }
}
```

该对象仅为接口草案；`strength` 的量纲、未知状态与错误枚举需在板屏验收后固定。

## Voice ↔ 工具网关 ↔ MQTT

### 规划中/未实现

语音模块不得直接发布任意 MQTT Topic。未来应经由独立工具网关完成意图校验、确认、授权、Topic 映射和结果回传：

```text
Voice intent
  → tool.request
  → policy/confirmation
  → mqtt.command.publish
  → mqtt.command.result
  → tool.result
  → Voice/UI
```

最小抽象：

| 类型 | 必填内容 | 约束 |
| --- | --- | --- |
| `tool.request` | `request_id`、工具名、结构化参数 | 不直接含 Topic、凭据或任意 Shell 命令。 |
| `tool.confirmation.required` | 风险描述、可展示摘要 | 危险动作必须等待用户明确确认。 |
| `tool.result` | `request_id`、`status`、可展示结果 | 区分接受、执行中、成功、拒绝、超时与失败。 |
| `mqtt.command` | 设备 ID、命令名、参数、过期时间 | 需可幂等并与 `request_id` 关联。 |

## RK3568 ↔ STM32

### 规划中/未实现

UART 适配器应只负责字节流、帧校验、重试和收发顺序；业务层只面对结构化设备命令和事件。

| 方向 | 抽象接口 | 职责 |
| --- | --- | --- |
| RK3568 → STM32 | `device.command` | 查询状态或请求受控动作。 |
| STM32 → RK3568 | `device.ack` / `device.result` | 分别表示已接受和最终执行结果。 |
| STM32 → RK3568 | `device.telemetry` / `device.fault` | 上报传感器、健康状态与故障。 |

具体帧编码、确认和错误码原则只在 [uart-protocol-draft.md](uart-protocol-draft.md) 中起草，尚未进入实现。

## Vision → UI / Voice / 工具网关

### 规划中/未实现

未来视觉模块应输出经过时间戳、置信度、来源设备与隐私策略约束的事件，例如 `vision.observation`；不得把原始图像、身份信息或未过滤文本直接送入语音工具执行链。视觉结果只能作为提示或待确认输入，不能自动触发危险设备动作。
