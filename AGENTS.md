# RK3568 项目工作规则

- 使用中文沟通，代码标识和注释使用英文。
- 新任务先阅读本文件与 `HANDOFF.md`；仅在任务需要时再查阅 `README.md`、`STATUS.md`、`ROADMAP.md`、`NEXT_TASK.md` 和目标源文件全文。
- 所有命令明确标注 `[Windows]`、`[VM]`、`[开发板]` 或 `[远程]`。
- 仓库根目录为 `D:\AProject\rk3568-ai-terminal`；语音、Qt、MQTT 分别位于 `apps/voice`、`apps/qt-ui`、`apps/mqtt-cloud`。
- Ubuntu VM/SDK 保留在 `D:\AIwork\rk3568-learning\Ubuntu_ATK-DLRK3568`，不移动、复制或纳入 Git。
- 厂商资料位于 `D:\RK3568`，只读使用；厂商 Qt 改动副本统一维护在 `platform/qt-system`。
- `local/` 仅保存机器相关脚本和访问配置，已被 Git 忽略。
- 不在回答、日志、文档或补丁中打印 API Key、密码和令牌。
- 新凭据只允许来自环境变量或未提交的本地配置。
- 开发板和 VM 地址使用前必须现场确认，不能盲用历史 DHCP 地址。
- 修改语音链路后至少执行 `tools\verify-local.ps1`；涉及板端行为时还要在板子上实际运行验证。
- 音频输入输出统一优先使用 16 kHz，避免 RK817 codec 采样率切换锁死。
- 文档检索先匹配实际开发/部署环境：Qt5 与桌面 Qt6、RKNN Toolkit 与板端 Runtime、Python 与 ARM64 库版本须分别核对；不能照搬最新版或不同环境的 API。通用库优先 Context7，RK3568/STM32、Buildroot 和厂商适配以本地 SDK、芯片手册及对应版本官方资料为准；资料不能代替板端实测。
- 删除、覆盖 VM 文件、板端部署目录或外壳模型前必须确认影响范围。
- 可视化协作：用户在 VS Code 打开工程时，代码修改前先说明目标文件与计划；每个可验证阶段完成后报告修改的文件、编译/测试命令、结果与日志路径。磁盘文件变更应让 VS Code 自然刷新；不能读取窗口画面时，必须明确说明，不得声称已观察到界面或物理现象。
- 任务引导：每次建议下一项工作时，明确指出应使用的 Codex 任务窗口，并给出建议的模型与思考强度；按任务复杂度选择，避免默认使用最高强度。
