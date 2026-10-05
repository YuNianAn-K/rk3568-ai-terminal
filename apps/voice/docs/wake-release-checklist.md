# 中文唤醒阶段提交与回退清单（2026-10-05）

本文件仅整理范围；没有暂存、提交、推送或新部署。实际仓库为
`D:\AProject\rk3568-ai-terminal`。整理时HEAD为
`45c53df34f0992ad270bac7954812c1df3a48c34`，暂存区为空。
当前功能仍在工作区和板端，不能把这个旧HEAD当作本次功能的回档点。

## 验收结论与边界

- 用户目视/听觉确认断网唤醒、本地问候、PC13亮灭、无人说话退出及恢复联网回复正常。
- 最新会话第15轮离线识别569ms；串口verified事务5ms，录音结束至verified690ms。
  计时起点必须区分；唤醒检测至verified为4435ms，含问候及用户说话，不是纯识别延迟。
- 第16轮no_speech退出，无ASR/LLM/LED；第17轮恢复MiMo ASR899ms、TTS862ms，走快捷回复。
  第14轮此前真正LLM首token830ms。恢复后的完整LLM路径未在这轮独立确认。
- 第9轮云端等待4026ms后离线拒识、无动作：保留这一限制，不称每轮成功或切换零等待。
- 最终idle、无错误、单一arecord、无aplay及auto.wav残留；RSS227064kB、7线程。
  属短时缓存后快照，不能据此证明无泄漏或计算漏/误唤醒率。
- 118项Python测试通过；Node、Qt Socket、15场景QML预览及两套Qt5 ARM64构建记录见
  `local/wake-entry-20261005/REPORT.md`。当前收尾只改文档，没有重新声称运行这些测试。
- 云台页面本次唤醒启停、复杂背景人声、自唤醒专项及长期性能没有全部独立验收。
  不做唤醒词与指令连说、打断或说话人隔离；保留按键备用和严格Action门槛。

## 待用户授权的Git提交范围

建议一个功能提交包含下列实现、测试和文档，方便整体恢复；提交前必须重新审查diff，
若期间其他窗口有新修改，按差异块区分，不使用 `git add .` 或按整个目录盲目暂存。
以下是当前候选清单，不保证未来同名文件中的所有改动都属于本任务。

语音入口、收音和提示：

```text
.gitignore
apps/voice/config/settings.py
apps/voice/main.py
apps/voice/voice_service.py
apps/voice/scripts/S99ai-voice
apps/voice/audio/capture.py
apps/voice/audio/vad.py
apps/voice/wake/sherpa_keyword.py
apps/voice/wake/keywords-xiaoai.txt
apps/voice/requirements-wake.txt
apps/voice/scripts/check_wake.py
apps/voice/assets/README.md
apps/voice/assets/wake-hello.wav
apps/voice/tests/test_voice_service.py
apps/voice/tests/test_chinese_wake.py
apps/voice/tests/test_hands_free.py
apps/voice/tests/test_silero_endpoint.py
```

两个现有Qt客户端的必要接入及验证：

```text
apps/qt-ui/aivoice/AppMainBody.qml
apps/qt-ui/aivoice/DiagnosticsPanel.qml
apps/qt-ui/aivoice/VoiceState.js
apps/qt-ui/aivoice/voicebridge.cpp
apps/qt-ui/aivoice/voicebridge.h
apps/qt-ui/aivoice/tests/Preview.qml
apps/qt-ui/aivoice/tests/preview_app.pro
apps/qt-ui/aivoice/tests/preview_main.cpp
apps/qt-ui/aivoice/tests/test_voice_state.js
apps/qt-ui/aivoice/tests/test_voicebridge.cpp
apps/qt-ui/aivoice/tests/voicebridge_test.pro
apps/qt-ui/gimbal-joystick/Main.qml
apps/qt-ui/gimbal-joystick/tests/render_person_ui.py
```

交接与复现文档：

```text
HANDOFF.md
apps/voice/README.md
apps/voice/docs/chinese-wake.md
apps/voice/docs/wake-release-checklist.md
apps/qt-ui/gimbal-joystick/VOICE_TRACKING.md
```

不纳入：local/、模型ONNX、vendor/vendor-wake、wheel、生成二进制、板端归档、私人录音、
config/config.py、.env、API Key、Wi-Fi/SSH访问配置、config/wake.enabled。
固定“你好”WAV不是私人录音，当前仅自用/展示；公开分发前另核对供应商条款。
不提交STM32、boot、视觉算法、MQTT或其他窗口新增内容。

建议提交说明：`feat(voice): add local Chinese wake and hands-free recording`。
授权后先核对暂存diff、排除秘密，再提交；记录生成的新commit号。Git只恢复源码，
不能自动恢复板端Qt二进制、模型、依赖和启用状态；这些必须按下列板端备份处理。

## 分层回退（本次未执行）

操作前重新确认现场IP、先ping/SSH身份核对，停止跟踪并等待语音idle。
不远程切断承载SSH的网络，不烧录、不绕UART锁、不删除整个目录。

1. **只关闭唤醒**：诊断页关闭唤醒，保留按键。永久关闭需在板端移除精确的
   `/root/AI_voice/config/wake.enabled`，确认无外部`VOICE_WAKE_ENABLE=1`后重启语音服务。
   这是非秘密启用标记，不动凭据。
2. **只恢复问候音**：备份
   `/root/AI_voice/.codex-backups/hello-tail-20261005-123255/`中的原WAV，
   在空闲时按相同路径原子恢复到`/root/AI_voice/assets/wake-hello.wav`；无需服务重启。
   当前0.68秒WAV SHA256为
   `437475baf240b455492a35f6c3cfc36bb65eca5f95a7815824651c494a65d9b4`。
3. **取消“你好”映射**：停止服务，按
   `/root/AI_voice/.codex-backups/wake-hello-20261005-122215/`清单恢复service，再启动。
   只恢复提示行为，不回退Qt/VAD；资产可留未使用。
4. **只回退Silero自动收尾**：停止服务，按
   `/root/AI_voice/.codex-backups/vad-endpoint-20261005-120517/`清单恢复
   capture.py及sherpa_keyword.py，再启动；旧能量端点有嘈杂时等待上限的已知问题。
5. **完整回退唤醒入口**：退出两套Qt/停止服务，按
   `/root/AI_voice/.codex-backups/wake-entry-20261005-114827/`manifest恢复
   main、service、settings、S99和两套Qt旧二进制这六个原文件；核对权限及哈希。
   关闭启用标记，新模型、库及未引用新文件可先保留。若以后清理，只移除manifest确认
   为本阶段新建的精确文件，不影响旧库、配置或其他窗口文件。恢复后验按键联网/离线控制。

本机对应归档保留在`local/wake-entry-20261005/`，不入Git；各归档哈希见REPORT及中文唤醒文档。
源码未来回退用针对本次commit的revert并重新构建/验证，不用`git reset --hard`覆盖共享工作区。
