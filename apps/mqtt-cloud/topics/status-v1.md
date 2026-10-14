# 第一版只读状态协议

协议版本 `1`；本轮只有 `get_status`，没有硬件动作、UART、摄像头视频或语音控制。
设备示例 ID `rk3568-01`，管理账号示例 `phone-owner`；上线前由用户确认实际标识。

| 用途 | 精确主题 | QoS / retain / MQTT 5 expiry |
| --- | --- | --- |
| 管理账号请求 | `rk3568/v1/devices/rk3568-01/request/phone-owner` | 1 / false / 15 秒 |
| 设备定向回复 | `rk3568/v1/devices/rk3568-01/reply/phone-owner` | 1 / false / 15 秒，消息体另受原请求截止时间限制 |
| 系统状态 / 离线通知 | `rk3568/v1/devices/rk3568-01/status` | 1 / true / 在线 30 秒、离线 60 秒 |

请求字段必须恰好是：`version=1`、`type=request`、24 位小写十六进制 `request_id`、
`sender=phone-owner`、`target=rk3568-01`、`action=get_status`、毫秒 Unix 时间 `issued_at/expires_at`。
截止时间大于当前时间，且 `0 < expires_at-issued_at <= 15000`；允许最多 1 秒的轻微时钟差。
双方需要正确的系统时间；
板端不会放宽检查来接受时钟不正确的命令。设备 ID / 管理账号只允许 `[a-z0-9][a-z0-9_-]{0,47}`。
主题中的管理账号必须与 `sender` 一致，Broker 的账号 ACL 必须约束精确请求主题，消息体身份本身不构成认证。
超过 4096 字节、重复 JSON 键、额外字段、未知版本/动作/账号/设备、过期、retained 请求均不采样、不回应。

回复带相同请求 ID、`sender=device_id`、`target=管理账号`、`action=get_status`、
`simulated=false`、`updated_at` 和原请求 `expires_at`。成功时 `data` 是当前真实状态快照；
采样入口失败时 `status=failed, reason=sample_unavailable`，不虚构状态。
网页只接受精确回复主题、非 retained、当前待处理请求、对应设备/账号和未过期的真实采样。
Broker PUBACK、原消息回传和电脑模拟回执均不代表真实设备查询成功。

在线状态字段：`version/type/device_id/session_id/online/simulated/updated_at/expires_at/capabilities/system`。
`capabilities` 只有 `get_status`；`system.source=linux-proc`，采样 `/proc/uptime`、`/proc/meminfo`、
`/proc/loadavg`，包含架构、运行秒数、内存 KiB、1 分钟负载。读取失败的字段为 `null`，并带 `sample_errors`。
没有云台角度、动作成功、灯状态或相机状态字段。测试夹具不代表板端真实状态。

每 10 秒采样一次。在线快照只在 30 秒内有效；网页每秒检查过期，断开云端时清除当前在线显示。
每次 MQTT 连接生成新 `session_id`；旧会话离线遗嘱和重复在线包不能复活已离线会话。
离线遗嘱在 CONNECT 前准备，不能获知断开时刻，因此 `online=false`、`updated_at/expires_at=null`。
它只证明代理连接离线，不证明板子断电。Broker 遗嘱检测还受到 20 秒 keepalive 和网络影响。

请求去重按管理账号/请求 ID，规范化 JSON 后比较内容，缓存回复 60 秒、上限 100 条。
相同请求不重复采样；同 ID 内容冲突或缓存已满时忽略，不淘汰未过期 ID。
重连不发送上一连接的缓存状态回复。进程重启会清空内存去重，不能宣称持久 exactly-once；
本版仅只读采样，不用于不可重复执行的动作。

设备采用 MQTT 5 clean start、session expiry 0、最大入站包 16384 字节、有限出站队列。
网络断开后新建客户端，避免旧出站 QoS 消息自动回放；网络失败按 2–30 秒退避。
认证、ACL 或 TLS 失败停止，须本机排查；不打印密码/异常细节，不降低 TLS、证书、主机名或 SNI 校验。
