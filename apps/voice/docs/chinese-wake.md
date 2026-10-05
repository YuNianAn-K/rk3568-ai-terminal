# 中文唤醒与免按键候选（2026-10-05）

状态：代码与本地验证通过，已部署；2026-10-05 用户基础现场验收通过，非完整稳定性验收。
最新现场证据、已知切换延迟、提交范围及回退边界见 [收尾清单](wake-release-checklist.md)。
下文“尚未执行/未部署”是部署前清单或历史验证阶段，部署事实见本节。不以单元测试代替真实录音验收。

## 本轮实际部署

### 听觉提示追加补丁

尾音后续：用户确认“好字后多了一截”，已只处理并替换固定音频，现0.68秒/21804字节，
SHA256 `437475baf240b455492a35f6c3cfc36bb65eca5f95a7815824651c494a65d9b4`。
前0.56秒样本完全不变，留80ms余量、20ms低幅尾部淡出、40ms零尾；没有改运行时收音代码。
原音频备份 `/root/AI_voice/.codex-backups/hello-tail-20261005-123255/`；恢复该文件即可回退，无需重启。
服务PID2712及代码哈希未变，118项本地测试通过。实际尾音是否消除/发音完整待用户确认。
以下0.96秒及SHA3032...为首次生成的原始资产信息。

最新用户映射：唤醒先播本地“你好”，无人说话退出播下面的 275 ms 叮咚。
“你好”使用现有 MiMo TTS 一次生成，`assets/wake-hello.wav`，16 kHz/mono/PCM16，0.96 秒，30764 字节。
SHA256 `3032b365adfed88becdf5d07074c29c2014524958a76cc426e543b8f20b042fb`；不是用户录音，无凭据。
唤醒播放期间麦克风已释放，播完再启动采集；运行时仅读本地文件，断网不请求 TTS。
文件校验单声道16k PCM16及最多1.5秒/50000字节，缺失或损坏则使用本地双音降级。
118 项测试通过，实际 WAV 本地读取/板端哈希一致，服务正常。尚未将真人听感与首字收音标记通过。
只部署新服务及 `/root/AI_voice/assets/wake-hello.wav`；服务备份
`/root/AI_voice/.codex-backups/wake-hello-20261005-122215/`，本机 `hello-backup.tar.gz`
SHA256 `c4366d8f2ab15c5d5b4360bbe41461a47dcd3cc039329a2a9652acccf821f645` 与板端一致。
回退本调整：idle时停止语音服务，恢复此备份 voice_service.py；新固定音频可留未使用，再启动服务。
无需回退 Qt、VAD 或任何模型。以下为上次提示方案，不能视为最新映射。

用户不看屏幕难以判断唤醒，批准本地双音试用。仅修改 `voice_service.py`：
唤醒 1046.5 Hz/110 ms + 25 ms 间隔 + 784 Hz/140 ms（共 275 ms），
无人说话退出 440 Hz/140 ms；PCM16/mono/16 kHz，峰值不超过 6000、8 ms 渐入渐出。
不修改硬件混音器或系统音量，不需要网络、TTS/模型、临时音频文件或新依赖。
沿用播放 2 秒超时；失败仅视觉反馈，仍可继续收音/恢复。
无声音仅对 hands-free、明确 no_speech、无错误且服务未停止的录音播放；正常回复、按键、取消和录音异常不播放。
无声退出音播放时服务仍忙，结束后才 idle/冷却/恢复监听，避免提示引起新轮。
116 项本地回归通过；备份 `/root/AI_voice/.codex-backups/earcon-20261005-121345/` 后部署服务文件。
仅回退本补丁：idle 时停止服务，恢复该目录 voice_service.py，保留 VAD/模型/Qt，再启动服务。
真实音量、音色辨识、播放防自唤醒与下一轮仍待用户确认。

### 自动收音追加补丁

用户反馈说完后等待太久：第 9/10 轮自动录音达到约 10.23 秒，ASR 本身 911/961 ms。
此前快速轮次是 manual_stop，不能视为自动收尾通过。旧能量端点遇持续背景能量可能无法计静音。
用户批准新增 [Silero VAD 模型](https://k2-fsa.github.io/sherpa/onnx/vad/silero-vad.html)，
原项目 [MIT 许可](https://github.com/snakers4/silero-vad/blob/master/LICENSE)。
采用 k2-fsa 官方发布的 16 kHz `silero_vad.onnx`，643854 字节，SHA256
`9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`。
无需新 wheel/密钥/服务；新增 `audio/vad.py`，修改 capture 和中文 wake 初始化以预加载并复用。
控制白名单及 ASR 置信度不变：VAD 只负责检测说话结束，不授权执行动作，不做说话人隔离。
0.8 秒静音尾部、4 秒无人说话、10 秒上限；检测输入去直流，原始 WAV 保留全部采样。
模型不存在时按原能量端点退回并打印 engine；模型存在但加载/推理失败时明确报错，不静默冒充成功。
原手动按键录音路径不使用新 VAD。短暂 0.6 秒停顿回归通过，仍需用户实际确认首尾字。

112 项本地测试通过。板端隔离实测模型加载 244–259 ms，4 秒静音/DC/60 Hz 嗡声
解码 278–330 ms，均 no_speech；官方模型包中文样音 speech=True/silence 自动结束。
两旧文件备份 `/root/AI_voice/.codex-backups/vad-endpoint-20261005-120517/`，本机 `vad-backup.tar.gz`
两端 SHA256 `6d47112f766d1abb13b5072f29f856215b930cf60d3176df784a43e6d9ae7be7`。
追加部署：`audio/capture.py`、`audio/vad.py`、`wake/sherpa_keyword.py` 到 `/root/AI_voice/` 对应路径；
模型到 `/opt/ai-voice-wake/silero_vad.onnx`；未替换 Qt 或其他语音文件。
新服务待唤醒、单一采集，RSS 99496 kB、短时单核 CPU 40.0%，无 auto.wav 残留。
真人自动收尾、停顿/截字及噪声环境效果待现场反馈；背景人声仍可能被判作说话。
仅回退 VAD：语音 idle 后停止服务，按追加备份 manifest 恢复 capture.py 与 sherpa_keyword.py，
新 vad.py 和小模型可暂留未使用，再启动服务。不要回退 Qt 或原唤醒部署；完整唤醒回退清单仍见后文。

### 首次唤醒入口部署

用户现场确认 `172.20.5.235`，先 ping 再核对 SSH 身份和旧版本哈希。
隔离 ARM64 静音检查：load 9051 ms，3 秒输入含尾部解码 596 ms，wake_hits 0，RSS 82960 kB。
首次隔离检查因临时包缺 __init__ 而无法导入，复用现有非秘密包文件后通过；不是正式服务故障。
备份目录 `/root/AI_voice/.codex-backups/wake-entry-20261005-114827/`；六个旧文件逐项哈希验证。
本机备份归档 `local/wake-entry-20261005/board-backup.tar.gz`，两端 SHA256
`0c8e323b0901ccdf3fbb981f59d407330295af2f693b94de09c7498e9c0e2b85`。
精确清单文件/模型/运行库已安装并创建空启用标记，两个 Qt 应用安装哈希与候选一致。
服务就绪为 idle/待唤醒，单一 arecord。5 秒采样 CPU 40.2%（单核口径）、RSS 99336 kB、6 线程；
新库实际磁盘 50500 KiB，模型目录 5336 KiB，auto.wav 计数 0。不是长期稳定性或真实语音成功率。
旧服务曾处理识别并缓存其他模型，新服务是初始化后采样，不能用 RSS 差值推断内存优化。
真实唤醒、收音、回复恢复、离线和云台动作仍待现场验收；先请用户进行两轮联网普通对话。

## 方案与来源

- `sherpa-onnx==1.13.8` CPU KWS，单推理线程；不需要账户或密钥，不持续上传待机音频。
- 模型 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`，chunk-16，int8 encoder/joiner + fp32 decoder。
  三图和 tokens 合计 5,448,042 字节；官方资料标注 chunk-16 算法延迟 320 ms，**不是板端实测唤醒时间**。
- [官方发布与使用说明](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html)。
- [运行库 Apache-2.0](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE)。
  发布 tar 包未附独立 LICENSE；已进一步读取
  [作者 ModelScope 模型卡](https://modelscope.cn/models/pkufool/icefall-kws-zipformer-zh-en-3M-2025-12-20)，
  `ReadMeContent` 声明 `license: Apache License 2.0`。
  对照作者公开 API `/api/v1/models/pkufool/icefall-kws-zipformer-zh-en-3M-2025-12-20/repo/files?Revision=master&Root=onnx`，
  三个采用的 ONNX SHA256 全部一致，不能只用运行库许可推断模型许可。
- 关键词 `x iǎo ài t óng x ué @小爱同学` 使用该模型的 phone+ppinyin 词表，加载前逐 token 核对；
  KWS 阈值 0.25、score 1.0、trailing blanks 2。它们不是 Vosk 的动作置信度阈值，原动作门槛不变。
- 模型及 wheel 不进入 Git；仅用户自用/展示。保留第三方许可与出处，公开打包前重新核对。

模型文件与 SHA256：

| 文件 | SHA256 |
| --- | --- |
| encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx | 408bbd740838c42d5bf6d1c5b80b3c88b616c7860b92d980328b5b068c76ae48 |
| decoder-epoch-13-avg-2-chunk-16-left-64.onnx | 63a22dd60f40fff082ac3e09afa507f6787da36df76ded2fbe145fa233e22c21 |
| joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx | 190d4067b4cc20b72a42a1916e69d92052000fb7051a427ebb1bc72a69207dc1 |
| tokens.txt | 2d3f32311f9b692b964da3c90e830258d3e78e013cb0c992dbfb15cd5a1a71b0 |

## 流程和接口

```text
voice_service 单实例 → idle 本地 raw PCM16/16kHz 监听
  → 中文关键词 → command_lock → 停止/回收监听 arecord
  → starting 状态 + 本地“你好”（缺失则本地音降级；播放失败仍显示视觉提示）
  → 无按键释放 sleep 的自动录音（另一个 arecord，但不同时持有麦克风）
  → Silero VAD ≥150 ms 活动 / 0.8 s 静音尾部 / 无声 4 s / 最长 10 s
  → 现有 WAV 质量检查 → MiMo 或 Vosk → 原受控 Action/聊天/TTS
  → 完整处理和播放退出 → 0.8 s 防回声冷却 → 恢复监听
```

待机 PCM 只送本地关键词检测，不落盘、不送 ASR。自动录音保留采集到的首段和尾部，
不截取“检测到活动之后”的片段；格式恒为 mono PCM16 16 kHz。输入停流 2 秒报错，
自动采集墙钟上限 12 秒。自动录音无人声或采集失败不调用 ASR/Action，临时 WAV 删除。

当前静音结束优先采用Silero，检测输入去直流；仅模型不存在时使用原能量端点降级。
不是说话人隔离，也不能保证房间内他人说话不会被收录；最长时限确保嘈杂时也能结束。
保留原 WAV 质量门槛、ASR 意图/置信度、安全白名单、串口及跟踪回执；没有改变控制范围。

原 `/tmp/ai-voice.sock` 路径、JSON Lines、`status/start/stop/cancel` 和事件结构不变。
只新增可选命令 `wake_enable/wake_disable`。仍使用 idle/starting/recording/recognizing/thinking/replying/playing/error。
idle 的 message 显示待唤醒，自动 recording 的 message 标明自动结束；新客户端据此显示提示。
两个客户端都订阅同一个服务，不创建后台服务、不启动另一 Qt 窗口，不因唤醒 requestActivate。
云台原窗口失焦停止保护不变；语音动作仍要求人物检测已打开并选中新鲜目标、位置已初始化。

模型缺失则回退按键，监听异常 5 秒后重试；释放麦克风失败不打开第二路采集。
诊断页可开/关唤醒（运行时开关）；没有处理期打断。长期听不到时仍可点麦克风。
旧英文 timer 模块留作历史，但正式 main/service 不引用它。

## 本轮验证证据

- `[Windows] tools/verify-local.ps1`：102 项测试通过，不是 100 轮板端压力测试。
  新测试覆盖精确关键词、英文拒绝、模型缺失、按键/唤醒并发、释放失败、无声/DC、停顿、最长时限、取消和恢复。
- `[Windows] node apps/qt-ui/aivoice/tests/test_voice_state.js`：通过。
- `[Windows] VoiceBridgeTest`：实际 Qt6 LocalSocket 往返通过（1 项测试 + init/cleanup），新轮清除旧文字且保留 wake timing。
- `[Windows] Qt6 实际语音页离屏渲染：15 种场景，0 failures、0 Qt warnings；已检查中文截图。
- `[VM] 两套现有 SDK Qt5 ARM64 构建通过，无 warning/error/undefined reference。
  构建仅在本轮 `/tmp/voice-wake-20261005-tKEhGZ`，不覆盖 VM 工程。
- 本机真实模型 2 秒静音 + 1 秒尾部：0 命中，解码约 47 ms、加载约 1.4 秒；仅是 Windows 样例，不是 RK3568 延迟。
- `[开发板] 只读核对：Python 3.10.5、aarch64、glibc 2.37、NumPy 1.26.4，
  MemAvailable 2880 MB，语音服务 RSS 241084 kB（约 235 MiB）、9 线程。
  这些是旧服务待机基线，**不是新增唤醒后的占用**。根分区可用约 4 GB。
- 唤醒 ARM64 wheel 在上一轮临时目录曾成功 import；当前重启后临时目录已不在，部署前须再次在隔离目录验证。
- 云台 QML 的自动录音展示回归已补充；当前桌面缺 PySide6，该脚本未运行。
  正式 Qt5 编译通过并不能替代其板屏/自动跟踪现场验收。

日志/候选位于仓库 `local/wake-entry-20261005/`，此目录不提交。
HANDOFF/README/VOICE_TRACKING 的旧描述按最新部署记录解释；本节为首次部署前验证历史，中文唤醒现已部署。

## 精确部署范围（尚未执行）

以下操作需要用户确认，届时重新核对 Git、板端 IP、空闲状态与每个目标哈希。先停止跟踪/退出 Qt，等语音 idle。
不远程断开 Wi-Fi、不触碰 UART 锁、boot 或固件。

| 本机来源 | 板端目标 |
| --- | --- |
| apps/voice/main.py | /root/AI_voice/main.py |
| apps/voice/voice_service.py | /root/AI_voice/voice_service.py |
| apps/voice/config/settings.py | /root/AI_voice/config/settings.py |
| apps/voice/audio/capture.py | /root/AI_voice/audio/capture.py |
| apps/voice/wake/sherpa_keyword.py | /root/AI_voice/wake/sherpa_keyword.py |
| apps/voice/wake/keywords-xiaoai.txt | /root/AI_voice/wake/keywords-xiaoai.txt |
| apps/voice/scripts/check_wake.py | /root/AI_voice/scripts/check_wake.py |
| apps/voice/scripts/S99ai-voice | /etc/init.d/S99ai-voice |
| local/wake-entry-20261005/aivoice | /opt/ui/src/apps/aivoice |
| local/wake-entry-20261005/gimbal-joystick | /opt/ui/gimbal-joystick/gimbal-joystick |

额外资产：只将上表三 ONNX 与 tokens.txt 安装到
`/opt/ai-voice-wake/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/`。
只用已下载的 CPython 3.10 ARM64 `sherpa_onnx` 和 `sherpa_onnx_core` 1.13.8 wheel，
在独立目录以 `--no-index --no-deps --target` 解包验证后安装到 `/root/AI_voice/vendor-wake`；
复用板端 numpy，不装 bin、sounddevice、soundfile、onnxruntime Python 或重编 Buildroot。
两份 ARM64 wheel 压缩合计约 16.7 MiB，解包内容约 49.1 MiB；实际板端磁盘/RSS 尚待安装后测量。
模型/库失败则不启用唤醒、不替换正式版本。

候选应用 SHA256：

- aivoice：`ec0d37d02863d4adb9216659913007b21efdcb7e0ad54c5584fc50a7d2349219`
- gimbal-joystick：`39ae3183c6e1ed6a81e06c41fc2f73917a6b81c7093f6b5269458a481e0615bc`

现板端只读基线（部署前必须重查，不把历史哈希当现状）：

- main.py：`93bb20e82a056888e11b7c0f3e2f10420a8551b2307413315e571886316b460e`
- voice_service.py：`956cf3d0b7b89dbc5fe75f8c20ee74b4ae999320cd39bb6fb8d48bf30e6dd6a0`
- aivoice：`410a5b8bb752d24587ee45ff6051f70a252731cda8a6520386946f0b9f0dceb9`
- gimbal-joystick：`2063abbb2f947395c495a6c699674e0f9c9aa66aeef38a1758de65e950d7abc4`

备份和部署顺序：

1. `[开发板]` 明确停止跟踪并退出两套 Qt，等待语音 idle；停止 S99 服务。
2. `[开发板]` 创建唯一备份目录 `/root/AI_voice/.codex-backups/wake-entry-<现场时间>/`，
   按部署表记录每个文件是否存在、模式和 SHA256；仅备份这些明确的文件。
   不备份/下载 `config/config.py`、.env、凭据或用户录音；记录新文件/新目录原先不存在。
3. `[Windows/远程]` 复制到唯一暂存目录，核对哈希、ARM64 runtime import 与 `scripts/check_wake.py` 静音检查；
   通过后才逐项安装必要文件。Qt 应用替换用同目录 `.new` + rename，保留权限；不用运行中的旧进程冒充新应用。
4. `[开发板]` 创建空的 `/root/AI_voice/config/wake.enabled`，不覆盖任何凭据配置；新 S99 只检查此非秘密标记。
   重启服务后验证待唤醒状态、单一 arecord、按钮备用；重开各 Qt 应用，核对 `/proc/<pid>/exe` 和新哈希。
5. 先在线验收，再由用户板屏断网，最后恢复热点并重新核对 IP，读脱敏耗时与结果。

回退：

- 仅关闭功能：诊断页“关闭唤醒/按键”，立即释放监听麦克风；这个开关仅本次服务运行有效。
- 永久按键启动：`[开发板]` 在 idle 时移除精确的非秘密文件 `/root/AI_voice/config/wake.enabled`，
  确保没有外部 `VOICE_WAKE_ENABLE=1`，重启服务；默认关闭。
- 完整回退：退出 Qt/停止语音服务，按本轮备份清单恢复被替换的 6 个旧文件（main、service、settings、S99、两 Qt 二进制）。
  只移除清单明确记为本轮新建的 capture、中文 wake 两文件、check_wake，以及启用标记。
  新模型/vendor-wake 可先保留未使用，之后按精确清单清理；不删除目录中原来存在的内容。
  不用 git reset，不回退其他窗口的视觉/固件改动。恢复哈希/权限后重启，核对按键联网和离线控制。

## 待现场验收和记录

每轮记录 wake_detected → wake_feedback_end → record_start → first_audio_frame → record_end →
ASR / offline_asr → Action 回执 / 首 token / playback_start → reply_end → round_end。
现有 `[VOICE]` 格式保留，仅新增 stage；记录录音时长、静音/无声/时限原因，不记录待机内容。

最小验收，不重复压力测试：

1. 不触屏：说“小爱同学”，提示音后普通对话；连做两轮。
2. 云台页先按原流程回中位/开启人物检测/选人，再唤醒说开始跟踪人物、停止跟踪；用户观察实物。
3. 用户从板屏断网：仍能唤醒后运行固定指令；若云台持有 UART，灯控应按原规则返回 busy，不能绕锁。
4. 恢复网络后普通 MiMo 对话正常，报告首次恢复的 ASR 路由和耗时。
5. 回答含唤醒词、播放期间旁人呼叫均不应触发新轮；播放后下一轮能正常唤醒。
6. 未唤醒、无人说话、未识别、否定/冲突指令均无动作。
7. 短句首尾、0.6 秒中途停顿、持续背景人声、超过 10 秒长句；记录截断/误收音，不将能量端点称为降噪模型。

短时间待机采样 `/proc/<语音PID>/status`、CPU 与 arecord 数量，列基线/启用后 RSS、CPU、
新库/模型实际磁盘占用、临时 auto.wav 是否残留。按真实尝试数报告漏唤醒/误唤醒；
无样本时填写“未测”，不写 0% 或完全稳定。用户确认实物动作和首尾是否完整。

限制：第一版两段式呼叫，不支持“唤醒词+指令”连说，不支持语音打断，10 秒录音上限；
持续他人声音可能延迟静音结束到上限。KWS 原生推理/ALSA 的板端持续性能仍需验收。
