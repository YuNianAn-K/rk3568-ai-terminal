# 板端只读状态代理

第一版代理已部署并完成一次真实只读 MQTT 联调。未设置常驻代理或自启动；
使用时仍需启动独立代理和本机网页服务。下方待测描述保留为历史阶段记录。
2026-10-14 实测：两个专用账号登录、电脑查询、8 项 ACL 负例、重复/过期请求、
正常退出/遗嘱/重连均通过；用户确认 iPhone 显示“查询完成 / 真实系统采样”。
电脑真实网页保持云端连接、暂停状态订阅后显示过期，恢复订阅后回到在线。
测试代理已正常退出，无自启动。证据：`local/mqtt/live-20261014/REPORT.md`。
重复使用的本机启动/停止窗口见 [`../tools/desktop/README.md`](../tools/desktop/README.md)。
手机消息与 MQTTX 双向收发已由用户确认；现有 echo ACL 保留。

## 历史部署与配置记录（当前验收以上方为准）

2026-10-13 后续部署：用户明确授权后，已在独立 `/opt/rk3568-mqtt-status-20261013/` 复制并核对 20 文件，
板端真实 `--sample` 和 Paho/CA 加载通过；没有常驻代理或自启动。
MQTT 业务查询与手机实机回执尚未验收。记录 `local/mqtt/DEPLOYMENT-20261013.md`。

2026-10-14 云端配置完成：`device-rk3568-01` / `phone-owner` 认证已创建，
下表精确主题权限及每用户最终 deny # 已保存、刷新后读回；原 echo 两条规则和消费限额 ¥0.00 保留。
控制台只支持主题/动作基础权限，没有配置 Broker 的 QoS/retain 细化限制。
账号 MQTT 登录与板端业务联调仍待实测。记录 `local/mqtt/CLOUD-CONFIG-20261014.md`。

## 依赖与运行边界

现场只读核对：板端 `ATK-DLRK3568 / aarch64 / Python 3.10.5`；系统 Python 未发现 Paho，
也未发现 Mosquitto CLI、libmosquitto 或 Node。VM 为 Python 3.8.10 / Mosquitto 1.6.9。
客户端固定 `paho-mqtt==2.1.0`（纯 Python，要求 Python >=3.7），不升级板端系统或 Python。
Context7 没有精确版本条目，已核对 [2.1.0 官方源码](https://github.com/eclipse-paho/paho.mqtt.python/tree/v2.1.0)。
网页继续使用已核实的 [MQTT.js 5.16.0](https://github.com/mqttjs/MQTT.js/tree/v5.16.0)，不升级浏览器包。

本机离线包位于 Git 忽略的 `local/mqtt/deps/`，官方 wheel SHA256：
`6db9ba9b34ed5bc6b6e3812718c7e06e2fd7444540df2455d2c51bd58808feee`，来源和校验记录在 `manifest.json`。
解压后的 `paho/` 与许可证已作为板端私有依赖目录复制，用 `--deps-dir` 指定；
没有在板端运行 pip install 或覆盖已有系统库，传输前后完整文件清单和哈希已核对。

## 已配置的专用账号和最小 ACL

下面的精确主题/操作规则已通过本人控制台保存并读回；未来调整前先审查原规则，不覆盖。
EMQX 客户端认证已创建 `device-rk3568-01` 与 `phone-owner`，密码由用户本机输入并保存。
不要把 App ID/Secret 用作 MQTT 密码；保留 `rk3568-test` 的 echo 规则和计费设置。

| 账号 | 操作 | 允许的精确主题 |
| --- | --- | --- |
| `device-rk3568-01` | 发布 | `rk3568/v1/devices/rk3568-01/status` |
| `device-rk3568-01` | 发布 | `rk3568/v1/devices/rk3568-01/reply/phone-owner` |
| `device-rk3568-01` | 订阅 | `rk3568/v1/devices/rk3568-01/request/phone-owner` |
| `phone-owner` | 发布 | `rk3568/v1/devices/rk3568-01/request/phone-owner` |
| `phone-owner` | 订阅 | `rk3568/v1/devices/rk3568-01/status` |
| `phone-owner` | 订阅 | `rk3568/v1/devices/rk3568-01/reply/phone-owner` |

每个账号按允许规则在前、最终 `#` 发布和订阅拒绝在后。客户端使用 QoS 1、请求/回复非 retained，
状态发布 retained，以支持在线快照和遗嘱。当前控制台表单没有 retain/QoS 细化控件，
不能把上述协议约定当作已经设置的 Broker 属性限制；设备会拒绝 retained 请求。
后续新增动作前再核对部署的协议级授权能力。不要添加“所有用户允许 #”。
网页无法单凭用户名判断 ACL 是否正确；必须验证设备账号无法发布请求、管理账号无法发布状态/回复，
且双方无法访问其他设备/其他管理账号主题。共用 echo 账号不算设备身份认证。

## 接入与验证步骤

以下步骤保留复现流程，首次在线联调已于 2026-10-14 完成，不再是当前待办。后续使用只在现场地址/版本变化时复核相应条件，不重复部署或全套测试。

1. 语音迁移收尾后，用户现场确认地址；有界 ping + SSH 主机公钥/hostname/arch 核对。
   地址变更时必须匹配已有可信公钥，不能关闭主机校验。`.255` 是广播地址，不能作目标。
2. 完成上述账号/ACL，使用现有域名，核对设备系统时间和 CA；TLS 地址必须用证书域名，不能改 IP。
3. 复制到新的独立目录（如 `/opt/rk3568-mqtt-status-20261013/`），保留已有业务和库。
   文件仅为 `status_agent.py`、`status_protocol.py`、离线 `paho/` / 许可证、CA 与本机配置。
   `config.example.json` 只是模板，实际配置置于独立目录，chmod 600；密码只来自 `MQTT_PASSWORD` 环境。
4. 先做无网络真实采样，再前台运行；不用 root 权限做硬件操作，不设置自启动。

```sh
# [开发板] 后续获准复制之后；config.local.json 中填实际域名/CA和独立账号，不包含密码
python3 status_agent.py --config config.local.json --sample
# MQTT_PASSWORD 由本机未跟踪凭据环境加载，不在命令行参数/聊天中填写
python3 status_agent.py --config config.local.json --deps-dir ./deps
```

5. 手机网页选择“真实设备状态”，设备 ID `rk3568-01`，用户名 `phone-owner`，输入管理账号密码。
   验证首次在线快照、查询匹配真实系统采样、请求非 retained、过期/重复/错设备拒绝。
   MQTTX 用管理账号仅订阅上述两个主题观察，不替代设备回应。
6. 对照板端 `/proc` 数值核对更新；退出代理确认离线通知，再测试非正常断连遗嘱、30 秒状态过期，
   重连旧请求不回放。记录真实手机/设备/账号负例后才宣告实机验收。

回退：前台 Ctrl+C 正常退出代理，确认离线/超时显示；停止这个独立进程即可恢复原业务。
保留独立目录便于核查，无需恢复固件、语音、Qt、网络或系统包。若以后需要移除目录，先确认精确路径。
云端专用账号可停用；保留既有 echo ACL。没有自启动或系统服务变更需要回退。

## 本地验证

```powershell
# [Windows] 仓库根目录；按本机 Python/Node 实际路径替换命令入口
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Join-Path $PWD 'local/mqtt/deps/paho-mqtt-2.1.0')
python -m unittest discover -s apps/mqtt-cloud/tests -v
node --test apps/mqtt-cloud/mobile-web/tests/*.test.mjs
```

协议细节见 `../topics/status-v1.md`。离线回归、网页渲染和板端只读环境证据在 `local/mqtt/REPORT.md`。
历史离线阶段只有 `--sample`，当时不等于 MQTT 实机验收；后续真实联调结果见本文件顶部。
后续启用前核对免费额度与消费硬限制为 0，不充值、不改计费；
每 10 秒一条心跳约 8640 条/天/设备，查询和订阅转发另计，不能假定永久免费无限使用。
