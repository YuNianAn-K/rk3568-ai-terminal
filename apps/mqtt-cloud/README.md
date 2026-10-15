# MQTT 与云端子项目

本目录用于 RK3568 终端的 MQTT、传感器接入和云端消息能力。它与语音、Qt 界面共用同一个 RK3568 Git 仓库，但保持独立模块边界。

## 当前基线

- Ubuntu VM 上的 Mosquitto Broker 与开发板客户端已完成发布/订阅验证。
- `mobile-web/` 提供 iPhone 网页 MQTT 测试、电脑模拟回执和真实板端只读查询；用户已确认 iPhone 显示真实查询完成。现有 echo 保留，硬件控制和视频未接入。
- `client/status_agent.py` 和 `topics/status-v1.md` 提供真实系统状态采样与只读 `get_status` 协议。专用账号、8 项 ACL 负例、过期/重复请求、正常退出/遗嘱/重连和网页状态过期恢复已完成一次真实联调；没有常驻代理。接入和回退见 `client/README.md`。
- `tools/desktop/` 提供手动启动/停止窗口，管理本次网页和独立板端代理；本机入口与运行配置放在忽略的 `local/mqtt/manual/`，使用说明见 `tools/desktop/README.md`。
- VM 与开发板地址由 DHCP 分配，任何联调前都必须现场确认。

## 计划结构

```text
apps/mqtt-cloud/
├── client/          # 板端 MQTT 客户端与重连逻辑
├── topics/          # Topic、消息 schema 和版本约定
├── tools/desktop/   # 手动网页/独立代理会话启动与停止
├── tests/           # 离线协议测试和 Broker 集成测试
└── README.md
```

## 设计边界

- Broker 地址、用户名、密码和证书只来自环境变量或未提交的本地配置。
- Topic 和消息体必须版本化；设备控制消息要有请求 ID、结果回执和超时。
- GPIO、继电器等危险动作必须经过白名单和用户确认，不能直接执行任意模型输出。
- MQTT 断线不能阻塞语音主链路；客户端应独立重连并提供明确状态。

## 下一步

1. 基础真实联调已完成，不重复布置账号/ACL 和手机首条查询验收；现有 echo 权限保留。
2. 后续使用时现场确认板端地址，再用 `tools/desktop/README.md` 的入口手动运行网页与独立代理；当前板端不能开机，不启动连接。
3. 保持只读状态查询范围，无自启动、不改系统依赖，不自动增加远程运动、视频或公网托管。
