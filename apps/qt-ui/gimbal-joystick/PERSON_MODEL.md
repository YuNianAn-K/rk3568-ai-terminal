# 人物检测模型与接口

本文记录默认CPU SSD链路与可选NPU试用后端。检测进程仅输出人物框，运动由原控制器执行。

## 模型来源

- 文件：`person_detection.tflite`，4,185,175 字节。
- 模型：量化 SSD MobileNet V1，COCO 类别；TensorFlow 官方示例的 metadata/2 版本。
- [官方下载脚本](https://github.com/tensorflow/examples/blob/master/lite/examples/object_detection/android/app/download_models.gradle)。
- [原始下载地址](https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/android/lite-model_ssd_mobilenet_v1_1_metadata_2.tflite)。
- SHA256：`cbdecd08b44c5dea3821f77c5468e2936ecfbf43cde0795a2729fdb43401e58b`。
- [TensorFlow 发布的模型卡](https://www.kaggle.com/models/tensorflow/ssd-mobilenet-v1/tfLite) 标明 Apache 2.0；许可全文保存在 `person_model.LICENSE`，取自 [TensorFlow models/LICENSE](https://github.com/tensorflow/models/blob/master/LICENSE)。
- 类别表在模型 ZIP 附件 `labelmap.txt` 中，首行是 `person`，输出类别索引为 **0**。不能沿用其他模型的 1-based COCO 编号。

worker 启动时核对 SHA256、类别表和输入/输出张量。换模型须显式更新并重新验收，不通过猜测张量顺序适配。

## 同帧链路

`QCamera → QVideoProbe → HandTracker` 的 RGB 预览帧同时交给 `PersonTracker`。
人物与手掌模式互斥；人物检测类不持有 GimbalBridge，不访问摄像头设备或串口。
原 worker 继续保持 UART 文件锁，人物模式不会另开串口。

输入为小端 uint32 字节数，再跟随 640×480×3 的 RGB 字节（921,600 字节，无行填充）。
人物 worker 把 RGB 直接缩放到 300×300，按 uint8 原值输入模型，不重复减 128 或除 255。
已验证输入量化参数为 scale 0.0078125 / zero point 128。
模型内 Detection_PostProcess 已执行后处理；输出框顺序为 ymin/xmin/ymax/xmax。

先输出一个 `ready` JSON 行，随后每帧输出一个 `result` JSON 行，包含从 1 起的 seq、
归一化的 left/top/right/bottom/score，以及预处理、推理、后处理、worker CPU/RSS。
仅保留 person，输出阈值为 0.40。2026-10-09 已安装的显示修复将显示与选择分开：
0.40 起显示候选，0.55 起可手动选择，自动选择仍要求 0.70 和连续三帧。
原目标持续关联允许 0.40；候选可见不代表目标确认或运动启动。
模型文件和张量契约不变，真实误检/漏检及修复后的板屏表现待验收。

2026-10-09 去重版已获授权安装：IoU 至少 0.65 的候选保留较高分框；低于 0.55 的小框
仅在被 0.55 以上的大框覆盖至少 90%、面积不超过其 75%、分差至少 0.08 时视为弱局部重复。
不能把包含关系当成人物身份：可靠的内嵌人物框仍保留，高度重叠的真实多人也可能被合并，需现场验证。
新弱候选要求三帧 IoU 至少 0.40 且关联无歧义；确认记录最多保留两个漏检结果，
仅输出当前帧框，不输出旧框或预测位置。接口增加 candidate_count 诊断字段，现有 Qt 忽略额外字段。

Qt 最多每 100 ms 尝试采样一次，且只允许一帧待推理，处理期间丢弃新帧。
框绘制按 PreviewItem 的 4:3 等比例内容区域映射，包含黑边偏移。
结果超过 1 秒不绘框；已有框超过 1 秒未刷新则清除。
画面停顿 1.5 秒、后续推理超过 2 秒、初始化/首次推理超过 10 秒、异常退出或坏输出会停止检测。
这些是显示阶段的边界；后续跟踪仍需满足原控制器 500 ms 帧龄限制并单独验收。

## 目标选择边界

首次单个较高置信度候选连续三帧时自动选框；多人时等待点击。通过框 IoU 关联相邻结果，不使用人物身份识别。
候选重叠过小或竞争候选接近进入最多 900 ms 恢复期，期间暂停运动。
关联综合框 IoU、尺度与中心连续性；尺度变化超过两倍时须两帧新鲜结果确认。
恢复期限从首次暂停开始，不因歧义或尺度确认重新计时；确认阶段不发送人物运动样本。
2026-10-09 真人复测后补充：目标在900ms搜索期内重新关联后，控制层最多另用600ms完成
三个不中断的新鲜样本确认，确认前双轴保持OFF。反复PERSON_PAUSE清空确认样本，
但不重启确认期限。持续缺目标仍900ms结束；总暂停预算最多1500ms，不延长旧帧运动。
持续丢失需要重新点击框并开始；不静默选择其他人。
人物交叉时几何关联仍可能无法分辨身份，当前阶段不得用于身份持续跟踪。

2026-10-09 全身/半身恢复隔离候选：普通IoU≥0.25路径保留；IoU≥0.15且顶边接近、
宽度相似、水平交叠足够的score≥0.55局部框，可以经两帧不同的新鲜结果确认。
两种框形态已确认后，900ms内与记忆形态高度相似且满足身体局部关系的当前框，
可避免反复触发尺度确认。记忆只用于关联，所有发送给控制器的框仍来自当前结果。
歧义暂停、固定恢复期限和500ms运动帧龄保留；不提供身份识别或旧框预测运动。
记录检测框接真实worker与模拟UART，前两段超时恢复问题可复现并恢复，持续无框段仍超时OFF。
Node/QML/人物PTY/Qt5构建和真实板端预览、STOP通过，真人连续跟随与机械顺滑度待验收。
候选 `/tmp/person-association-20261009/app`，正式20文件未替换；详见本机
`local/person-association-20261009/REPORT.md`，正式替换前须重新备份和验证。

2026-10-09 连续性候选将 CPU 推理改为三线程。静态样图中位约 84 ms，
两线程约 111 ms；四线程 P95 波动较大，未采用。静态基准不能代替整机并发与真人准确率验收。
人物控制对取帧时PWM补偿后的绝对目标使用200ms时间常数平滑，暂停时重置，
不累加保留图像误差；每轴60ms单档80us、240us领先量及500ms帧龄边界不变。

## 2026-10-03 已验证范围

- 现有板端 Python 3.10.5、cv2 4.5.4、numpy 1.26.4、tflite_runtime 2.14.0 可加载此模型；未安装新系统包。
- SDK qmake/make 交叉编译通过；原位置续接及延迟反馈回归通过。
- 板端隔离 Qt5 测试覆盖 RGB 帧、单帧等待、摄像头不可用、重启、结果顺序错误、过期结果和进程退出；测试不打开摄像头或 UART。
- 黑帧及官方 Grace Hopper 静态图片各 30 帧，前 3 帧预热；黑帧检出 0 人，人物图检出 1 人。
- 人物图推理中位 108.259 ms / P95 110.121 ms；管道写入至结果中位 120.928 ms / P95 123.989 ms。
- 人物图 worker CPU 中位 183.35%（单核口径，约 1.83 核）；RSS 81,492 KiB。该数值不包含 Qt。
- 桌面 Qt6 对实际 QML 使用测试相机/框数据渲染，检查中文、布局、点击及丢失状态；不能替代板端 Qt5 实物验收。

上述为隔离软件验证。随后已在用户授权后部署正式应用并启动同一路实际相机。
初次取回的 339 帧日志中，检测频率中位约 5 Hz，推理中位/P95 为 118.481 / 124.891 ms，
Qt 取帧至结果中位/P95 为 147 / 154 ms；预览帧交付约 15 FPS，不是屏幕实际绘制 FPS。
45 秒资源采样记录 Qt RSS 中位 123,138 KiB、worker RSS 中位 81,784 KiB；
该采样期间存在人物检测的启停，详见本地 `live-summary.json`，不能当作长期基线。
已取回的日志中，人物模式时段无运动命令；手掌与手动操作发生在其他时段，不计入人物检测验收。
目视框/置信度/目标状态、多人误检漏检、最终退出释放和长期表现仍待验收记录。
静态样图不代表真人场景的检出率，不代表相机曝光至屏幕或机械总延迟。

## 2026-10-09 配对采集与候选淘汰

显式设置 `PERSON_CAPTURE_DIR` 才启用后台配对采集；默认关闭。保存640×480 RGB PNG与
同帧JSON（原始person候选、去重框、最终框、模型SHA和推理计时），目录跨重启最多40组。
单框场景每2秒、其他场景每1秒采样，队列上限2；写盘失败隔离并关闭采集，不中断检测。
本次用户采集32组；这是稀疏诊断采样，不能用于估计全帧漏检率或运动抖动。

`tests/compare_person_models.py` 在开发板同一32张图片上回放两个固定SHA模型。
人工判读17张完整可见真人：正式SSD最终16张单框、1张双框；10张空场景两者均无框。
EfficientDet-Lite0在这17张回放中均单框，但不能用SSD原始多框数量代替正式最终显示框数量。
边缘/遮挡5张不作为准确率验收；未采到独立袋子误检对照，袋子问题仍未解决。

EfficientDet仅在独立临时应用目录试用，来源为
[TensorFlow官方示例下载配置](https://github.com/tensorflow/examples/blob/master/lite/examples/object_detection/android/app/download_models.gradle)，
模型SHA `2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b`。
实机113帧检测约3Hz；预热后推理中位/P95 266.272/296.338ms，取帧至结果296/323ms。
112次相邻结果交接时，上一帧年龄均超过500ms，中位610ms，最大716ms；
在现有控制边界下会造成暂停，不能靠延长旧帧驱动掩盖这个问题。
48帧最终有两个框，未采集本轮画面，不能仅凭日志判定真假人物。
因此不采用该CPU候选；正式模型、600ms恢复确认及500ms帧龄限制保持原值。
候选退出确认相机Unloaded、双轴OFF且无应用/检测/控制残留。
详细证据保存在本机 `local/person-evidence-20261009/REPORT.md`，下一步应验证硬件加速的
检测链路性能，再评估真人误检漏检和连续跟随，不能宣称本轮识别质量已修复。

## 2026-10-09 RK3568 NPU隔离候选

显式 `PERSON_DETECTOR_BACKEND=rknn` 才加载新增 `person_rknn.py`；默认仍为SSD，
未知后端报错停止。NPU不打开相机或串口，使用原Qt RGB帧和ready/result协议。
正式目录本轮未替换，隔离应用在 `/tmp/person-npu-20261009/app/`，保留完整哈希清单。

使用厂商资料 `rknn_yolov5_demo.zip` 内已转换的
`RK3566_RK3568/yolov5s-640-640.rknn`，在试用目录命名为 `person_detection.rknn`。
7624064字节，SHA256 `544bdbe8b26a86f065b4479a4eeff5541a68a7366205f5e55f1069218108d398`。
源码仓库不包含这个可选二进制；部署须从厂商资料提取并验证此SHA，不能随意换同名模型。
厂商80类表首项person=0，配套demo说明模型使用ReLU；不据此宣称准确率改善。

现有开发板RKNN runtime 1.5.2、驱动0.9.2实际通过初始化与推理，未更新系统。
绑定限定本轮验证版本，启动核对模型SHA、输入/输出数量、形状、类型和量化契约。
原生头文件与ctypes结构尺寸、偏移在VM核对一致，实际板端查询再核对。
输入是640×640 uint8 RGB，按厂商demo直接缩放；模型属性为int8，使用runtime的
uint8→模型输入转换。输出为三个int8 NCHW logits头，分别80/40/20网格。
CPU解码施加零点/比例及Sigmoid，只有person胜出80类比较且objectness×class至少0.40才保留，
IoU>0.45做person NMS，最多10框，再复用既有局部框过滤及连续弱候选确认。
模型结果中的raw_boxes已完成YOLO NMS；raw_person_proposals记录此前proposal数量。

32张同图回放中，人工判读的17张完整可见人物均单框，10张空场景均无框。
推理中位/P95 54.623/65.824ms，完整预处理+推理+解码88.551/99.710ms。
可选检测进程静态人物10帧管道中位/P95 108.293/119.011ms，CPU约52.2%单核口径；
黑帧无人物。采样小且无标准标注，不能推算完整准确率，袋子误检与真实跟随仍待验收。
真实Qt预览、窗口状态和匹配STOP OFF通过，已打开供用户进行检测复测。
500ms帧龄、歧义暂停、900ms搜索+600ms确认、限位、控制节奏与STOP均未改。
本机详细证据：`local/person-npu-20261009/REPORT.md`。

本轮真人复测最终包含两段1362/167帧，共1529帧。第一段检测中位约7Hz，
推理51.2ms、取帧至结果112ms/P95 145ms；追加段推理51.020ms、结果112ms、约6.8Hz。
两段相邻结果交接的上一帧年龄最大分别360/363ms，均未超过500ms；
第一段检测进程CPU中位37.61%单核口径。
40组配对画面证实悬挂格子衣物仍有0.52–0.74的误检，近距离/遮挡真人会漏检。
双框中也包含真实背景人物，不能把全部双框当误检。实际9次跟随会话38次暂停、29次恢复，
7次控制器超时、2次界面关联丢失停止；不能宣称流畅度验收通过。
保持比例输入的离线对照仅减少部分误检，亦新增漏检与NMS后局部框；
该对照未经过最终连续候选过滤，不能直接等同于最终显示重复框，未部署。
备用s_relu模型算子提交失败后停止，另两个备用模型未测试，未升级系统。
原legacy模型复查仍正常；用户退出后相机Unloaded、双轴OFF、无应用/检测/控制残留。
因此保留当前NPU链路作为隔离开发基础，当前模型与输入方案尚不作正式替换。

## 验证入口

### 2026-10-09 YOLOv8可选候选

显式 `PERSON_DETECTOR_BACKEND=rknn-v8` 使用新 `person_rknn_v8.py`，默认SSD和旧rknn后端不变。
可选资产 `person_detection_v8.rknn` SHA256
`36566148f41a51ba192ca44423e32238223d3a77e9fe11e8618c2b5d0c0c6ecd`，不包含在源码仓库；
由官方YOLOv8n ONNX用匹配1.5.2工具转换，独立20张COCO校准，用户72图只作对照。
输入RGB上下各80像素零填边；DFL还原坐标后去填边，类别输出已Sigmoid，不能重复应用。
启动固定runtime 1.5.2、driver0.9.2、1输入9输出形状/类型/量化契约；复用现有候选过滤与协议。
旧17完整真人均单框、10空场景无框，9张明确悬挂衣物负例未再检出衣物，仍有近距离漏检与弱局部框。
72图全流程中位/P95 82.894/90.315ms；真实预览运行时静态进程管道87.697/101.814ms。
静态结果不代表连续身份保持、Qt帧龄或机械流畅度验收。
Windows与板端5项V8、5项V5、10项SSD回归通过，真实预览/STOP OFF通过。
隔离目录 `/tmp/person-npu-opt-20261009/app` 已打开供真人复测，正式20文件未变；
完整证据 `local/person-npu-opt-20261009/REPORT.md`，正式替换前须备份和验证。

```powershell
# [Windows] 无推理库依赖的结果/协议测试
py -B apps/qt-ui/gimbal-joystick/tests/test_person_detector.py
# [Windows] 使用现有 Node.js 执行目标关联测试
node apps/qt-ui/gimbal-joystick/tests/test_person_targets.js
```

```sh
# [VM] 独立测试二进制，使用现有 SDK
source /home/alientek/toolchain/environment-setup
cd apps/qt-ui/gimbal-joystick/tests
qmake persontracker_test.pro
make -j2
```

`persontracker-test` 只能与 `tests/fake_person_detector.py` 放在独立测试目录运行；
将该 fixture 命名为测试目录的 `person_detector.py`。**不能覆盖正式 worker。**

```sh
# [开发板] 已确认 IP、ping 和串口空闲后，在独立测试副本运行
python3 -B tests/benchmark_person.py --frames 30 --image /path/to/stored-image.jpg
```

基准工具只读静态输入，不打开相机或串口。桌面渲染测试用已有 PySide6 执行
`tests/render_person_ui.py --output /path/to/test-output`，界面明确显示“输入为模拟框”。
