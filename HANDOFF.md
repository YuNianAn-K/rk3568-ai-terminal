# RK3568 当前项目交接

更新时间：2026-10-03（人物检测与双轴跟随已部署，用户基础实物测试正常，退出收尾已核对）

## 新任务先读的当前事实

2026-10-05 中文唤醒基础验收收尾：用户确认断网唤醒、本地“你好”、PC13实际亮灭、
无人说话叮咚退出及恢复联网均成功，尾音听感已接受。最新记录覆盖下方“待反馈”的历史条目。
日志第15轮离线识别569ms，LED回读verified耗时5ms，录音结束至verified为690ms；
第16轮no_speech退出且无ASR/Action，第17轮恢复MiMo ASR 899ms及TTS正常（快捷回复，非LLM）。
第14轮此前有真正LLM首token830ms；不能据此宣称恢复后的LLM已单独验收。
最终idle/has_error=false、单一arecord、无aplay和auto.wav残留，RSS227064kB、7线程；
这是缓存离线模型后的短时快照，不代表长期无泄漏。118项本地回归通过。
仍有第9轮云端等待约4026ms后离线拒识，不能宣称网络切换零等待或所有轮次成功。
未量化漏/误唤醒率；本次云台页面启停跟踪及复杂背景人声未独立分项验收。
提交范围与分层回退见 `apps/voice/docs/wake-release-checklist.md`。仅整理文档，未暂存/提交/推送；
当前HEAD为45c53df34f0992ad270bac7954812c1df3a48c34，不是包含本次功能的Git回档点。

2026-10-05 问候尾音已替换：用户说明刚才断网并要求重试，ping/SSH身份/现场IP172.20.5.235核对通过。
仅原子替换 `/root/AI_voice/assets/wake-hello.wav`，新0.68秒/SHA437475ba...；原音频备份
`/root/AI_voice/.codex-backups/hello-tail-20261005-123255/`，本机 wake-hello-before-tail.wav 对应原始版。
服务代码SHA6e5e064d...及PID2712未变，没有重启、修改收音/识别或再次请求TTS。
本机正式资产已同步，118项回归通过；实际“好”字完整及尾音听感仍待用户再次确认。
回退仅恢复该备份中的wake-hello.wav，不回退服务或其他文件。下条为断网时的未部署阶段记录。

2026-10-05 问候尾音候选：用户确认“好字后面多了一截”。原0.96秒WAV在约0.56秒后为低幅残留。
仅生成候选 `local/wake-entry-20261005/wake-hello-tail.wav`：前0.56秒采样完全不变，
保留80ms余量、末20ms淡出、补40ms零尾，总0.68秒；原音频本机备份已保留。
候选SHA256 `437475baf240b455492a35f6c3cfc36bb65eca5f95a7815824651c494a65d9b4`。
118项回归通过，本机正式资产仍是旧SHA3032b365...；未更改服务/收音代码。
部署尝试因当前172.20.5.235 ping及有界SSH均超时中止，尚未确认板端替换，不能宣称生效。
须用户重新提供现场地址后仅备份/替换WAV、不重启服务，再确认真实尾音听感。

2026-10-05 提示映射调整：用户要求唤醒先说“你好”，将叮咚用作无人说话退出。
已用现有板端 MiMo TTS 仅生成一次固定“你好”，保存在 `apps/voice/assets/wake-hello.wav`
并部署至 `/root/AI_voice/assets/`，16 kHz/mono/PCM16、0.96 秒、30764 字节，无凭据或私人录音。
后续唤醒不联网合成，播放结束才收音；缺失/损坏时降级本地双音，不阻塞云端。
118 项测试及实际 WAV 读取通过。只替换服务和新音频，旧服务备份
`/root/AI_voice/.codex-backups/wake-hello-20261005-122215/`，本机 hello-backup.tar.gz 两端哈希一致。
服务 PID2712 idle/待唤醒、单一arecord、RSS99040 kB、无录音残留。听感、首字及无声退出等待现场反馈。
Qt、VAD/ASR/Action和固件未改；未提交推送。下条是之前的提示映射。

2026-10-05 本地听觉提示补丁：用户批准“先试试”。仅修改 voice_service.py，唤醒双音
275 ms、无人说话退出低音 140 ms，PCM16/mono/16 kHz，幅度上限 6000、渐入渐出，播放超时 2 秒。
播放期间不恢复监听，不调用云端；按键/正常回复/录音错误不播无声退出音。
116 项本地测试通过；已校验备份并部署，旧服务文件位于
`/root/AI_voice/.codex-backups/earcon-20261005-121345/`，新服务 PID 2626。
实际可听见、音量适当、无声退出提示和下一轮仍待用户试用；不宣称听觉验收通过。
另：上一版 VAD 用户反馈“挺快的”，日志最新 3 轮均 silence 自动收尾、总采集约 2.8–3 秒，
录音完成至 ASR 请求 93–116 ms，ASR 723–933 ms；最后 idle/无错误/auto.wav 0。
这是短句阶段验证，不代表背景人声、无人说话与断网等全部通过。

2026-10-05 自动收音 VAD 补丁：用户同意“试试”。已接入 Silero 小模型，沿用现有 sherpa-onnx
运行库，16 kHz/单推理线程，预加载后复用；0.8 秒静音尾部、4 秒无语音退出、10 秒最长时限，原 WAV 不截取。
仅新增 audio/vad.py、调整 audio/capture.py 与 wake/sherpa_keyword.py；Qt、ASR/Action 门槛和固件不变。
112 项本地测试通过；板端隔离静音/DC/60 Hz 嗡声负例和官方中文样音正例通过，加载约 0.25 秒。
已备份并部署，旧两文件备份 `/root/AI_voice/.codex-backups/vad-endpoint-20261005-120517/`；
本机 `local/wake-entry-20261005/vad-backup.tar.gz` 两端 SHA256 一致。新服务 PID 2501 idle/待唤醒，
单一 arecord、RSS 99496 kB、5 秒采样单核 CPU 40.0%、临时 auto.wav 0。
真实普通音量自动收尾/截字/无人说话退出待用户反馈，不声称问题已彻底解决。下条为修复前诊断。

2026-10-05 唤醒现场问题更新：用户反馈说完话仍长时间等待识别。板端第 9/10 轮录音
约 10.23 秒，到 ASR 请求约 10.94/10.99 秒；ASR 自身 911/961 ms。
auto_endpoint 日志有多次 max_duration，此前较快几轮为 manual_stop，不能称自动静音收尾已通过。
代码 SilenceEndpoint 仅用能量，speech_detected 后噪声基线不再更新，持续背景能量可能阻止静音计时；
当前日志没有逐帧指标，尚未实测噪声频谱/来源。不以缩短最长录音代替修复。
建议复用已安装 sherpa 运行库接入小型 Silero VAD，需先向用户说明额外模型与资源影响；
本轮尚未下载该模型、修改或部署端点补丁。云台/断网其他验收暂缓。

2026-10-05 中文唤醒部署更新：用户确认“可以，开始吧”并现场确认板端仍为 `172.20.5.235`。
ping/SSH 身份、四个旧核心版本哈希一致；隔离 ARM64 模型静音检查通过，随后按清单部署。
六个旧文件备份 `/root/AI_voice/.codex-backups/wake-entry-20261005-114827/`，本机归档
`local/wake-entry-20261005/board-backup.tar.gz` 与板端 SHA256 一致。
新版服务 PID 2160，Socket idle/待唤醒、单一 arecord，短时待机 CPU 约单核 40.2%、RSS 99336 kB、6 线程；
无 auto.wav 残留。两套新版 Qt 哈希一致，AI语音已重新打开。真实唤醒/收音/在线离线/云台动作仍待用户现场反馈。
不把静音检查或服务就绪写成完整验收；未提交/推送，未触碰 boot、固件、UART 或凭据。
下条为部署前记录。

2026-10-05 中文唤醒候选：真实仓库已核对，开始时 Git 干净。新增 sherpa-onnx
中文 KWS“小爱同学”、麦克风互斥交接、自动静音收尾、无声退出和按键备用，
接入同一 voice_service 与 AI语音/云台客户端，不切页、不改变跟踪保护和 Action。
102 项 Python 回归、Qt Socket/实际语音页渲染测试及两套 VM Qt5 ARM64 构建通过。
仅只读核对板端，尚未部署；唤醒命中/误触、断网、自唤醒、首字尾字、待机资源待现场验收。
模型作者 Apache-2.0 声明和 ONNX 哈希已核对。部署清单见
`apps/voice/docs/chinese-wake.md`，本地候选/日志在 `local/wake-entry-20261005/`。
不提交 Git，部署须用户确认。后文“唤醒尚未接入”指正式板端；早期“语音跟随未部署”已由后续部署记录覆盖。

2026-10-05 正式部署：用户回复“进行”，现场确认板端 `172.20.5.235`，完整备份云台目录 18 文件到 `/opt/ui/.codex-backups/ui-flow-20261005/`，板端与本机归档均校验通过。仅替换云台应用，新 SHA256 `2063abbb2f947395c495a6c699674e0f9c9aa66aeef38a1758de65e950d7abc4`；其他云台文件及语音源码未变。真实 Qt5 首帧/相机、控制接口及 STOP off 通过，语音 idle；板屏布局与结果保留检查待用户反馈。记录 `local/ui-flow-20261005/REPORT.md`。下条为本次部署前的开发记录。

2026-10-05 界面收敛更新：用户批准继续，已完成云台页按钮移出画面、人物模式提示、语音识别/回执分区及停止结果保留。仅本地 QML 预览、81 项语音回归和 VM Qt5 构建通过，尚未部署；候选 `2063abbb2f947395c495a6c699674e0f9c9aa66aeef38a1758de65e950d7abc4`。记录 `local/ui-flow-20261005/REPORT.md`；正式板端仍为下列 10 月 3 日语音跟随版本，整机稳定性测试按用户要求留后。

- 实际仓库为 `D:\AProject\rk3568-ai-terminal`。Codex 保存的项目入口是父目录 `D:\AProject`；开始任务须确认 Git 根目录。旧语音窗口仍显示迁移前副本路径，不能把其 cwd 当作当前源码目录。
- 板端约 3.72 GiB 总内存，按 4 GB 级别规划；联网使用 MiMo ASR/LLM/TTS，离线只处理固定指令，不部署本地大语言模型。
- UART9 M1 `/dev/ttyS9` ↔ STM32 USART1 PA9/PA10、PC13 灯控和 boot 持久化已验证。摄像头、双轴云台与外部供电已到货并用于现场实验。
- UVC 已完成 1080p MJPEG 与 640×480 YUYV 取流、样帧和板屏预览。正式 Qt“云台摄像”安装在 `/opt/ui/gimbal-joystick/`，第二页有入口，不开机自启。
- 现有视觉闭环是 Qt 同帧取流/预览 → MediaPipe 来源的 TFLite 手掌检测（CPU）→ 有界控制 → UART → STM32 双轴 PWM。最新版用户反馈“效果还可以，后面可以继续优化”；没有宣称精确同步跟随或完整稳定性通过。
- CPU TFLite Person 检测、人物框/置信度、目标选择和双轴人物跟随已部署，用户反馈“测试完了，正常”。多人交叉和长期表现未单独验收。语音开始/停止跟踪已部署并获本轮基础实物有效反馈；RKNN/NPU 和中文唤醒词尚未接入。
- 云台应用运行时独占 UART9 文件锁，其他灯控/云台事务会 busy。未来语音启停跟踪应调用应用的受控入口，协调状态和串口所有权。
- 当前进入语音启停人物跟随：云台应用提供受控本地入口，语音复用录音与识别服务，通过应用协调串口所有权。具体范围见 `NEXT_TASK.md`。
- 语音启停候选开发与隔离验证已完成，未部署：81 项本地语音回归、实际 QML 模拟界面、VM 交叉编译及板端 Qt5 控制/检测测试通过。候选与验证记录见 `local/voice-tracking-20261003/REPORT.md`，正式应用仍是下列人物跟随版；真实录音联动待验收。

2026-10-03 后续部署更新：用户要求“备份了可以开始”，完整备份 20 文件逐项校验通过，板端目录 `/opt/ui/.codex-backups/voice-tracking-20261003/`，本机归档 `local/voice-tracking-20261003/board-backup.tar.gz` 再次校验通过。七项候选已安装，语音服务重启后 idle；新版应用 SHA256 `b9c62ad8c7c2dda5396a80186de5310b6bdb38185c5755348c5514627bb0e21f`，worker `93b0b1e98081099715b3a884433ded584e935a706a8df8ce4a4f1a6261d24bfa`。实际相机预览初始化、错误目标拒绝和关联 STOP 双轴 OFF 回执通过；用户已反馈“测试完毕，有效果”；日志确认语音开始 active、停止 off 均 accepted=True，退出后应用/worker 无进程、摄像头无打开描述符、应用/UART 锁释放，语音 idle。联网/离线分项和长期稳定性未单独验收。首次检查未等待初始化而触发回退，修正就绪等待后安装成功；固件、模型及 voice_service.py 未改。前面的“未部署”条目是部署前阶段记录。

## 当前版本与证据

- 2026-10-03 当前人物跟随版本：应用 SHA256 `0f8c055fe43a1f8648cfae17a4f9978ae07121ff7d05aff0ab672fa18e4c67c2`，worker `6c48671194d812b3f4609431a9c442a8e3dcfca312bf5d6c131349f59c6640c2`；固件未改。用户基础实物测试正常，退出后 PONG、PAN/TILT/TRK OFF、摄像头与应用/UART 锁释放均核对通过。记录 `local/person-follow-20261003/REPORT.md`；检测版回退备份 `/opt/ui/gimbal-joystick.pre-person-follow-20261003/`。下列 9 月版本为历史。

- UVC：`local/uvc-acceptance-20260928/`，任务“RK3568｜已完成：UVC 摄像头取流验收”。设备节点受枚举顺序影响，使用前按 USB 身份重新确认，不固定沿用 `/dev/video10` 或 `/dev/video0`。
- 云台：`apps/qt-ui/gimbal-joystick/README.md`、`local/gimbal-resume-fix-20260930.md`；任务“RK3568｜视觉云台：手掌跟踪与优化”（`01a0d6e1-5f69-7ba0-8310-cb3749929de1`）。旧记录与旧哈希保留历史意义，最新应用 SHA256 为 `22ff21ba2c766bdfb726351268995282d936d86d1bc74f2f732d53db5b19c4aa`，worker 为 `a1913906366b996c121d993789af87d4ab6003d839c5845ea2b2ffabcc305316`，固件 HEX 为 `f172dd084a22eb50aa0ff65925b9506a4c2f4c8d35d7ab374b0f04832e0a3b60`。
- 跟踪参数：Pan 500–2500 µs、Tilt 750–2250 µs，斜坡最多 24 µs/20 ms；STM32 2 秒失联停止。重新上电位置未知，显式回中位后启动；停止保留 RAM 中输出脉宽，不能感知外力移动，也不是机械角度反馈。
- 最新实验结束时已有 PONG / PAN OFF / TILT OFF / TRK OFF 与串口锁释放记录。本轮没有再次实时查询；供电电压、电流、真实轴角和最新版本的持续性能仍未量化。
- 语音：任务“RK3568｜语音：MiMo、离线控制与唤醒词”（`01a0319d-7812-7d03-a785-91cea91b7283`）2026-09-26 记录 Wi-Fi 在线但无互联网的 4 轮离线灯控约 0.6–0.8 秒完成回读，1 轮未匹配未动作，恢复联网后可对话。仍为阶段展示版本；唤醒词停在诊断准备。
- 应用/worker 的上一版备份：`/opt/ui/gimbal-joystick.pre-feedback-20260930/`；启动修复前备份：`/opt/ui/gimbal-joystick.pre-resume-20260930/`；固件/源码配套备份：`local/gimbal-resume-rollback-20260930/`。回退必须核对应用、worker 与固件协议兼容，不能任意混搭；本轮未执行回退。
- Git 有多窗口未提交修改，`stm32/`、`apps/qt-ui/gimbal-joystick/` 和部分文档尚未跟踪。9 月交接仅同步文档与窗口名称；10 月人物跟随部署及语音候选开发以本节首条和当前事实为准。未提交或推送。

## 窗口职责

| 窗口 | 使用范围 |
| --- | --- |
| RK3568｜总控：审查、下任务与工作总结 | 维护现状、交接和下一任务范围；整体决策 |
| RK3568｜视觉云台：手掌跟踪与优化 | 现有云台应用、手掌模型和控制修复的历史与续接；同时涉及 STM32 跟踪固件 |
| RK3568｜已完成：UVC 摄像头取流验收 | UVC 基础验收证据，阶段已结束 |
| RK3568｜语音：MiMo、离线控制与唤醒词 | 语音链路与唤醒词实验历史；后续执行先确认真实仓库路径 |
| RK3568｜UI：情绪核心与 Qt 界面重构 | aivoice 布局、表情与动画，不负责人物检测 |
| RK3568｜历史：STM32 接入与 UART9 验证 | STM32 基础接入、UART9 boot 与 PC13 阶段记录；最新云台状态以上节为准 |

后续新阶段采用短任务和明确交接；当前没有创建新窗口。更细的长期状态见 `STATUS.md`，历史材料按任务需要查阅。

## UART 基础与镜像回退记录（历史阶段）

以下保留 2026-09-24 的 UART 阶段证据，不能用该阶段的完成范围覆盖上面的最新状态。

### UART 阶段结论

- STM32F103C8T6 的独立 USART1 固件已用 Keil 编译（0 Error、0 Warning）、经 ST-Link 下载，并通过串口和 PC13 LED 实物验收。原 PC13 最小闪烁工程保留，未被覆盖。
- RK3568 UART9 M1 候选镜像已获授权写入 boot 分区；写后回读、热重启和实际断电冷启动后的整分区 SHA256 均与候选镜像一致。`/dev/ttyS9` 在冷启动后自动出现，`ttyFIQ0` 仍为 Linux 调试控制台。
- 冷启动后 `PING\r\n → PONG\r\n`、`LED?\r\n → LED=OFF\r\n` 已通过。写入后的完整 LED 开关及状态回读通过，用户目视确认 PC13 LED 闪烁后熄灭。本阶段不需要重复硬件压力测试。
- UART 收尾时为 ASCII 灯控协议，联网 PC13 已目视验收；后续已扩展 PAN/TILT/TRK 舵机控制及离线固定语音，最新范围见上文。二进制 CRC 与传感器仍未实现。

### 工程与接口

- UART 固件工程：`stm32/firmware/stm32f103c8t6-uart-link/Project.uvprojx`；回退用最小闪烁工程：`stm32/firmware/stm32f103c8t6-minimal/Project.uvprojx`。
- STM32 USART1：PA9 TX、PA10 RX；RK3568：UART9 M1 `/dev/ttyS9`。115200、8N1、无流控，双方 3.3V TTL，TX/RX 交叉、GND 共地；不将两端 3V3 电源并联，不接 5V 到信号线。
- 已验证命令：`PING → PONG`、`LED ON → OK`、`LED OFF → OK`、`LED? → LED=ON/OFF`、未知非空命令 `→ ERR`；请求与回复以 `\r\n` 结束。PC13 低电平点亮。
- 板端最小检查脚本：`tools/uart-smoke.py`；协议状态与未来方案：`docs/uart-protocol-draft.md`；构建、接线及详细验收见 `stm32/README.md`。

### 镜像、备份与回退

以下文件均保留在仓库外，不应加入 Git：

| 用途 | 原始位置 | 大小（字节） | SHA256 |
| --- | --- | ---: | --- |
| 原始 boot 备份 | `D:\AProject\rk3568-uart9-work\boot-before-uart9.img` | 67,108,864 | `f369d3f0dbc2bcea461f28b82e375dd5d23e7bcce7262e77fd4a47f7cd540b59` |
| 已写入的 UART9 候选 boot 镜像 | `D:\AProject\rk3568-uart9-work\safe-build-20260921\boot-uart9-1080p-external-64MiB.img` | 67,108,864 | `c7e1c1a6d4774529541c83da50b418d25d25353225aa0775a6d67f76aeaef34f` |
| RAM 临时启动用 FIT | `D:\AProject\rk3568-uart9-work\safe-build-20260921\boot-uart9-1080p-external.fit` | 37,023,232 | `f239290083095239a400f4954e6a0782b83594a44a60aca8765c3bca7f628d53` |
| 候选 FIT 所用 resource | `D:\AProject\rk3568-uart9-work\safe-build-20260921\resource-uart9-1080p.img` | 1,114,112 | `33d962f490f9065496f8ac4aba02175d5fcaea1f571619a83edd3d3f09a35671` |

候选镜像专用回退脚本：`D:\AProject\rk3568-uart9-work\restore-ums-boot-uart9-candidate.ps1`。默认只读预检，真正恢复需要额外授权及 `-Execute`；离线模拟和物理 UMS 只读预检已通过，**未做过实体回退写入**。旧版 `restore-ums-boot.ps1` 针对旧候选哈希，不适用于当前镜像。不要沿用历史 UMS 磁盘号。

### UART 阶段验收证据

- 本地验收记录（Git 忽略）：`local/uart9-diagnostics-20260923/permanent-boot-write-20260923.md`、`stage1-acceptance-20260923.log`、`stage2-flash-acceptance-20260923.log`。
- Keil 构建/下载日志（Git 忽略）：`stm32/firmware/stm32f103c8t6-uart-link/build-keil-20260923.log`、`flash-keil-20260923.log`。
- 联网语音控制 PC13 已另行实施：明确的“打开指示灯”“关闭指示灯”经 MiMo ASR 后进入严格白名单，串口发送后核对 `OK` 与 `LED?` 回读；用户已目视确认 PC13 先亮后灭。代码见 `apps/voice/main.py`、`apps/voice/tools/pc13_led.py`，板端日志见 `/var/log/ai-voice.log`。离线固定命令的后续现场结果见上文。
- 其他历史待办（如系统 Settings 新热点真实密码连接验收）仍见 `STATUS.md`；不要将其误记为 UART 阶段未完成。

### UART 阶段边界

UART9 boot 已持久化，无需为后续软件任务重复改写。不使用 `ttyFIQ0` 传业务数据。STM32 固件已在后续云台任务中更新，版本见当前交接；Wi-Fi/SSH 地址由现场网络分配，历史 IP 仅可作线索。各窗口未提交改动继续保留。
