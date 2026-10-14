# MiMo 全链路迁移与验证

## 2026-10-13 对话模型 V2.6 迁移记录

只升级对话模型到 `mimo-v2.6-flash`；ASR仍为`mimo-v2.5-asr`、TTS仍为`mimo-v2.5-tts`。
保持`thinking.type=disabled`、SSE正文流、原分句及PCM16/mono/16k路径，不升级库、不改变Qt协议。
来源：[官方V2.6公告](https://mimo.mi.com/docs/en-US/news/latest/v2-6)、
[Chat Completions文档](https://mimo.mi.com/docs/en-US/api/chat/openai-api)；
Context7 `/websites/mimo_mi_en-us` 同时核对模型名、thinking及stream字段。
旧默认/板端显式配置均为`mimo-v2.5`，仅更新默认及板端的`MIMO_MODEL`赋值。

`[Windows] tools/verify-local.ps1` 121项通过：新增默认模型与ASR/TTS保持不变、
环境覆盖回退、流式正文/分句及不播reasoning_content回归。第一次受沙箱缓存写入权限阻止，
通过审批后运行通过，不是功能测试失败。
Windows验证使用现有Python3.12环境；板端Python3.10.5、requests2.34.2，未更新依赖。

板端现场地址经ping/SSH身份核对后迁移；旧PID936，新PID1162，初始化后idle。
部署仅`/root/AI_voice/config/settings.py`、`/root/AI_voice/llm/mimo.py`和
未提交的`/root/AI_voice/config/config.py`中的`MIMO_MODEL`值；AST比较确认其他配置不变。
备份`/root/AI_voice/.codex-backups/mimo-v26-20261013-112128/`。
原配置备份仅留板端，目录0700、文件0600，不复制至电脑或Git。

新文件SHA256：

- settings.py：`dcaa37b4480f20722a4a9a15699a2fde915c8186fea72e4a489b9d5d3e644e97`
- llm/mimo.py：`d602f7f89a5fe364ebc0aa55816fbe7426a0eb69d06369c6026efa15c844fd21`

部署后`[开发板] python3 scripts/check_mimo.py --online`不设模型覆盖变量，PASS。
真实LLM走`chat_stream`，不是本地快捷回复；合成文本检查通过，未打印回答。
非流式TTS1595ms，ASR969ms，LLM首正文8778ms/完整10785ms，
流式TTS首PCM681ms/完整1580ms、9块、97280字节，输出16k。
部署前临时指定新模型的一次检查也PASS，LLM首正文3358ms/完整3507ms。
这是两次短API采样，延迟波动明显，不能宣称升级提速、平均延迟或完整麦克风闭环验收。
未使用`--play`，不争抢声卡；真实唤醒录音、播报听感及下一轮由用户现场确认。
详细非敏感记录见Git忽略的`local/mimo-v26-20261013/REPORT.md`。

回退：先重新核对现场地址并等语音idle，停止服务；按上述备份恢复settings.py和llm/mimo.py，
只把当前本地配置的`MIMO_MODEL`改回`mimo-v2.5`，保留期间其他配置/密钥修改，再启动并验证。
完整原配置是板端应急备份，不盲目覆盖后续凭据或配置；不回退Qt、唤醒模型、VAD、离线控制或固件。
本轮未提交/推送Git，未写根目录交接文件，由总控集中整理。

### 部署后用户真实试用日志核对

2026-10-13用户已亲自试用，随后只读检查`/var/log/ai-voice.log`最新服务会话，
仅提取阶段与耗时，不输出语音/回复内容。PID仍为1162，模型仍为V2.6 Flash/disabled；未重启或新增API调用。
以下时刻由日志`t`转换为UTC+8，明确属于本次试用，不把后续Settings/SystemUI更新的事件混入：

| 轮次/唤醒时间 | 路径和收尾 | ASR | LLM首字符/完整 | 首次TTS至播放 | 唤醒至首播/整轮 |
| --- | --- | --- | --- | --- | --- |
| 1 / 20:38:32 | Silero silence；真实LLM流式回答 | 1205ms | 6950 / 7594ms | 1051ms | 15699 / 25375ms |
| 2 / 20:39:07 | VAD判no_speech；本地退出提示 | 未调用 | 未调用 | 未调用云端TTS | 无回答播放 / 5741ms |
| 3 / 20:39:15 | Silero silence；local_response快捷回复 | 648ms | 未调用 | 1194ms | 4921 / 7524ms |

第1轮问候约900ms、采集4753ms，录音结束至ASR请求202ms，
录音结束至首个回复播放9982ms；首字符至首次TTS请求559ms，
首播至reply_end跨度9671ms（可能含后续分句合成，非单独纯音频时长）。
第3轮采集2044ms、录音结束至ASR请求69ms。三轮均有round_end与wake_listen active，
第2轮无ASR/LLM/设备Action调用；no_speech只能证明VAD判定，不能证明用户未说话或已发生漏识别。
用户试用事实已确认，但没有具体听感评价；软件播放阶段不能替代扬声器声音质量确认。
当前idle/round3/无错误、RSS105512kB、7线程、单一arecord、无aplay与/tmp/*.auto.wav残留。
未在本次会话提取到错误阶段；只核对有限三轮，不计算识别成功率、漏唤醒率或长期稳定性。
可确认真实LLM完成后能进入下一轮；不能将第3轮快捷回复写成第二轮完整LLM验收。
迁移基本链路有效，主要等待仍是LLM首字符，不能宣称提速或完全稳定；本轮仅补充记录，不改代码。

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
