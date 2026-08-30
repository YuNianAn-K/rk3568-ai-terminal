# RK3568 项目工作规则

- 使用中文沟通，代码标识和注释使用英文。
- 修改前先阅读 `README.md`、`STATUS.md`、`ROADMAP.md` 和目标源文件全文。
- 所有命令明确标注 `[Windows]`、`[VM]`、`[开发板]` 或 `[远程]`。
- 仓库根目录为 `D:\AProject\rk3568-ai-terminal`；语音、Qt、MQTT 分别位于 `apps/voice`、`apps/qt-ui`、`apps/mqtt-cloud`。
- Ubuntu VM/SDK 保留在 `D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`，不移动、复制或纳入 Git。
- 厂商资料位于 `D:\RK3568`，只读使用；厂商 Qt 改动副本统一维护在 `platform/qt-system`。
- `local/` 仅保存机器相关脚本和访问配置，已被 Git 忽略。
- 不在回答、日志、文档或补丁中打印 API Key、密码和令牌。
- 新凭据只允许来自环境变量或未提交的本地配置。
- 开发板和 VM 地址使用前必须现场确认，不能盲用历史 DHCP 地址。
- 修改语音链路后至少执行 Windows 语法检查；涉及板端行为时还要在板子上实际运行验证。
- 音频输入输出统一优先使用 16 kHz，避免 RK817 codec 采样率切换锁死。
- 删除、覆盖 VM 文件、板端部署目录或外壳模型前必须确认影响范围。
