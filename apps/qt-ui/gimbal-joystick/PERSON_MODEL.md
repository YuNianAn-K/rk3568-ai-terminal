# 人物检测模型与接口

本阶段仅显示人物框和目标状态，CPU 推理；不发送人物跟踪运动命令。

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
仅保留 person，初始置信度阈值为 0.55；该阈值须用真实场景继续评估。

Qt 最多每 100 ms 尝试采样一次，且只允许一帧待推理，处理期间丢弃新帧。
框绘制按 PreviewItem 的 4:3 等比例内容区域映射，包含黑边偏移。
结果超过 1 秒不绘框；已有框超过 1 秒未刷新则清除。
画面停顿 1.5 秒、后续推理超过 2 秒、初始化/首次推理超过 10 秒、异常退出或坏输出会停止检测。
这些是显示阶段的边界；后续跟踪仍需满足原控制器 500 ms 帧龄限制并单独验收。

## 目标选择边界

首次只有一人时自动选框；多人时等待点击。通过框 IoU 关联相邻结果，不使用人物身份识别。
候选重叠过小或竞争候选接近时判为丢失，需要重新点击框；不静默选择其他人。
人物交叉时几何关联仍可能无法分辨身份，当前阶段不得用于身份持续跟踪。

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

## 验证入口

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
