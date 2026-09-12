# MiMo 全链路迁移与验证

## 生效范围

默认提供方为 MiMo ASR、MiMo 对话和 MiMo TTS。Qt 与 `/tmp/ai-voice.sock` 的 JSON Lines 协议没有变化，Wi-Fi 模块不在本次修改范围。

录音仍固定为 16 kHz、单声道、PCM16 WAV。MiMo ASR 只接受经过该格式检查的录音；MiMo TTS 的 24 kHz 流式 PCM 在写入 ALSA 前持续重采样为 16 kHz。流式 TTS 只允许在首帧播放前降级，开始播放后发生中断则停止本句，避免重复播报。

## 配置

优先使用进程环境中的 `MIMO_API_KEY`。为兼容现有开发板，可设置 `VOICE_LOCAL_CONFIG` 指向板上未提交的旧配置文件；该文件由安全的 AST 解析器读取，不会被执行，也不需要复制到测试目录。

可选开关：

- `VOICE_TTS_ENGINE=mimo|edge|pyttsx3|gtts`
- `LLM_ENGINE=mimo|glm`
- `MIMO_TTS_STREAM=1|0`
- `MIMO_TTS_VOICE=mimo_default`
- `MIMO_ASR_LANGUAGE=auto|zh|en`

## 验证命令

以下本地测试不访问真实 API：

```powershell
# [Windows]
cd D:\AProject\rk3568-ai-terminal
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
```

VM 不是 Python 语音服务的必经构建环节；只有需要传输或排查网络时使用，并先现场确认地址：

```bash
# [VM]
hostname
hostname -I
```

开发板地址每次从板端现场读取，不能照抄历史 DHCP 地址：

```bash
# [开发板]
hostname
ip -4 addr
python3 --version
/etc/init.d/S99ai-voice status
```

在独立临时目录完成离线测试后，可复用正式目录中的本地配置做少量真实 API 冒烟测试。命令不会显示密钥；`--play` 会占用声卡，必须先停止正式语音服务再使用：

```bash
# [开发板] 在临时验证包的 apps/voice 目录中
VOICE_LOCAL_CONFIG=/root/AI_voice/config/config.py python3 -m unittest discover -s tests -p 'test_*.py'
VOICE_LOCAL_CONFIG=/root/AI_voice/config/config.py python3 scripts/check_mimo.py
VOICE_LOCAL_CONFIG=/root/AI_voice/config/config.py python3 scripts/check_mimo.py --online
```

## 正式部署前检查

- 板端 `hostname`、IP 和 SSH 主机指纹与现场信息一致。
- 正式服务处于空闲状态，没有正在录音或播放。
- `/root/AI_voice/config/config.py` 已单独留存在板端，部署包内没有该文件。
- `MIMO_API_KEY` 对 ASR、对话和 TTS 三个模型均有权限。
- 离线测试通过，真实 API 冒烟测试通过。
- 记录当前 `/root/AI_voice` 备份路径和服务状态，再停止服务、部署并启动。
- 用板屏实际说一句非本地快捷问题，确认识别文本、流式回答、首句播放、回到 READY 和紧接着的第二轮都正常。

## 回滚

正式目录回滚应停止服务，将部署前代码备份恢复到 `/root/AI_voice`，保留现有 MiMo 本地配置后再启动服务。不要用 Git 命令覆盖板端凭据。百度 ASR 与火山 TTS 已退役，不能再作为回滚目标。
