"""Replay paired lossless frames on two pinned models; no camera or UART."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import zipfile

CONFIG = {
    'ssd': ('cbdecd08b44c5dea3821f77c5468e2936ecfbf43cde0795a2729fdb43401e58b', 300, 10,
            ['TFLite_Detection_PostProcess' + suffix for suffix in ('', ':1', ':2', ':3')]),
    'efficientdet': ('2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b', 320, 25,
                     ['StatefulPartitionedCall:' + suffix for suffix in ('3', '2', '1', '0')])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--ssd', type=Path, required=True)
    parser.add_argument('--efficientdet', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import cv2
    import numpy as np
    from tflite_runtime.interpreter import Interpreter
    cv2.setNumThreads(1)
    inputs = []
    for metadata in sorted(args.frames.glob('frame-*.json'))[:40]:
        record = json.loads(metadata.read_text(encoding='utf-8'))
        image = cv2.imread(str(metadata.with_suffix('.png')))
        if image is None:
            continue
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        assert list(rgb.shape) == [480, 640, 3], 'unexpected saved RGB shape'
        assert hashlib.sha256(rgb.tobytes()).hexdigest() == record['rgb_sha256'], 'frame mismatch'
        inputs.append((metadata.name, rgb))
    assert inputs, 'no complete paired frames'
    result = dict(frames=len(inputs), models={}, results=[],
                  limitation='Saved frames only; score calibration differs by model. No identity or mechanical accuracy claim.')
    for name, (sha, size, maximum, names) in CONFIG.items():
        path = getattr(args, name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, 'model hash mismatch'
        with zipfile.ZipFile(path) as archive:
            assert archive.read('labelmap.txt').decode().splitlines()[0] == 'person'
        model = Interpreter(model_path=str(path), num_threads=3)
        model.allocate_tensors()
        inp = model.get_input_details()[0]
        assert list(inp['shape']) == [1, size, size, 3] and inp['dtype'] == np.uint8
        by_name = {item['name']: item for item in model.get_output_details()}
        assert set(by_name) == set(names), 'unsupported output mapping'
        outputs = [by_name[key] for key in names]
        for item, shape in zip(outputs, ([1,maximum,4], [1,maximum], [1,maximum], [1])):
            assert list(item['shape']) == shape and item['dtype'] == np.float32
        # Identical stored input for each model, three warmups before timing.
        for _ in range(3):
            model.set_tensor(inp['index'], cv2.resize(inputs[0][1], (size,size))[None])
            model.invoke()
        timings = []
        for filename, rgb in inputs:
            model.set_tensor(inp['index'], cv2.resize(rgb, (size,size))[None])
            begin = time.monotonic()
            model.invoke()
            elapsed = (time.monotonic()-begin)*1000
            timings.append(elapsed)
            boxes, classes, scores, count = [model.get_tensor(item['index'])[0] for item in outputs]
            assert np.isfinite(count) and 0 <= count <= maximum
            people = []
            for box, label, score in zip(boxes[:int(count)], classes[:int(count)], scores[:int(count)]):
                assert np.isfinite(box).all() and np.isfinite(label) and np.isfinite(score)
                if label != 0 or not .4 <= score <= 1:
                    continue
                top,left,bottom,right = [max(0.,min(1.,float(value))) for value in box]
                if right <= left or bottom <= top:
                    continue
                people.append(dict(left=left,top=top,right=right,bottom=bottom,score=float(score)))
            result['results'].append(dict(frame=filename,model=name,raw_boxes=people,
                                          inference_ms=round(elapsed,3)))
        result['models'][name] = dict(sha256=sha,threads=3,
            inference_ms_median=round(statistics.median(timings),3),
            inference_ms_p95=round(sorted(timings)[round((len(timings)-1)*.95)],3))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('frames','models','limitation')}))


if __name__ == '__main__': main()
