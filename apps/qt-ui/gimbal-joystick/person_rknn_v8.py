"""Pinned RK3568 YOLOv8 backend; Qt RGB input only, no camera or UART.

DFL decoding follows the Rockchip model-zoo export and Apache-2.0 demo.
"""
import numpy as np
import ctypes as C
import hashlib
from pathlib import Path
import time
from person_rknn import Attr, Counts, Input, Output, Version, checked, load_api, query

MODEL_SHA = '36566148f41a51ba192ca44423e32238223d3a77e9fe11e8618c2b5d0c0c6ecd'



def decode(outputs, threshold=.4):
    if len(outputs) not in (6, 9):
        raise ValueError('unexpected YOLOv8 output count')
    proposals = []
    per_branch = len(outputs) // 3
    for branch, grid in enumerate((80, 40, 20)):
        position, classes = outputs[branch*per_branch:branch*per_branch+2]
        if position.shape != (1, 64, grid, grid) or classes.shape != (1, 80, grid, grid):
            raise ValueError('unexpected DFL/class contract')
        if not np.isfinite(position).all() or not np.isfinite(classes).all():
            raise ValueError('nonfinite model output')
        # Rockchip export applies Sigmoid to classes; DFL remains logits.
        if classes.min() < -.01 or classes.max() > 1.01:
            raise ValueError('class output is not probability')
        scores = classes[0, 0]
        y, x = np.nonzero((scores >= threshold) & (classes[0].argmax(axis=0) == 0))
        if not len(y):
            continue
        logits = position[0, :, y, x].reshape(-1, 4, 16)
        weights = np.exp(logits-logits.max(axis=2, keepdims=True))
        distances = (weights*np.arange(16)).sum(axis=2)/weights.sum(axis=2)
        stride = 640/grid
        for xx, yy, dist, score in zip(x, y, distances, scores[y, x]):
            left = max(0., (xx+.5-dist[0])*stride/640)
            top = max(0., ((yy+.5-dist[1])*stride-80)/480)
            right = min(1., (xx+.5+dist[2])*stride/640)
            bottom = min(1., ((yy+.5+dist[3])*stride-80)/480)
            if right > left and bottom > top:
                proposals.append(dict(left=float(left), top=float(top), right=float(right), bottom=float(bottom), score=float(score)))
    return proposals


def nms(boxes, threshold=.45):
    kept = []
    for box in sorted(boxes, key=lambda b: b['score'], reverse=True):
        area = (box['right']-box['left'])*(box['bottom']-box['top'])
        for other in kept:
            overlap = max(0., min(box['right'], other['right'])-max(box['left'], other['left'])) * max(0., min(box['bottom'], other['bottom'])-max(box['top'], other['top']))
            other_area = (other['right']-other['left'])*(other['bottom']-other['top'])
            if overlap/(area+other_area-overlap) > threshold:
                break
        else:
            kept.append(box)
            if len(kept) == 10:
                break
    return kept


class Detector:
    def __init__(self, model):
        data = Path(model).read_bytes()
        if hashlib.sha256(data).hexdigest() != MODEL_SHA:
            raise ValueError('YOLOv8 model checksum mismatch')
        self.lib, self.context = load_api(), C.c_uint64()
        buffer = C.create_string_buffer(data)
        checked(self.lib.rknn_init(C.byref(self.context), buffer, len(data), 0, None))
        try:
            self.version = query(self.lib, self.context, 5, Version())
            if not self.version.api_version.decode().startswith('1.5.2 ') or self.version.drv_version.decode() != '0.9.2':
                raise ValueError('unverified RKNN runtime/driver version')
            counts = query(self.lib, self.context, 0, Counts())
            if (counts.n_input, counts.n_output) != (1, 9):
                raise ValueError('unexpected YOLOv8 IO count')
            inp = query(self.lib, self.context, 1, Attr(index=0))
            if list(inp.dims)[:inp.n_dims] != [1,640,640,3] or inp.fmt != 1 or inp.type != 2 or inp.qnt_type != 2:
                raise ValueError('unexpected YOLOv8 input contract')
            self.attrs = [query(self.lib, self.context, 2, Attr(index=i)) for i in range(9)]
            for index, attr in enumerate(self.attrs):
                grid = (80,40,20)[index//3]; channels = (64,80,1)[index%3]
                if (list(attr.dims)[:attr.n_dims] != [1,channels,grid,grid] or attr.fmt != 0 or attr.type != 2 or attr.qnt_type != 2 or attr.n_elems != channels*grid*grid or attr.size != attr.n_elems or not np.isfinite(attr.scale) or attr.scale <= 0):
                    raise ValueError('unexpected YOLOv8 output contract')
        except Exception:
            self.close()
            raise

    def close(self):
        if self.context.value:
            checked(self.lib.rknn_destroy(self.context))
            self.context.value = 0

    def detect(self, rgb):
        if rgb.shape != (480,640,3) or rgb.dtype != np.uint8:
            raise ValueError('unexpected RGB frame')
        begin = time.monotonic()
        # Export/reference use zero padding. Qt still receives original-image boxes.
        image = np.zeros((640,640,3), np.uint8)
        image[80:560] = rgb
        inp = Input(index=0, buf=image.ctypes.data, size=image.nbytes, type=3, fmt=1)
        checked(self.lib.rknn_inputs_set(self.context, 1, C.byref(inp)))
        prepared = time.monotonic()
        checked(self.lib.rknn_run(self.context, None))
        outputs = (Output*9)(*[Output(index=i, want_float=1) for i in range(9)])
        checked(self.lib.rknn_outputs_get(self.context, 9, outputs, None))
        invoked = time.monotonic()
        try:
            arrays = []
            for out, attr in zip(outputs, self.attrs):
                if not out.buf or out.size != attr.n_elems*4:
                    raise ValueError('unexpected YOLOv8 output buffer')
                array = np.ctypeslib.as_array(C.cast(out.buf, C.POINTER(C.c_float)), shape=(attr.n_elems,))
                arrays.append(array.reshape(tuple(attr.dims)[:attr.n_dims]))
            proposals = decode(arrays)
            boxes = nms(proposals)
        finally:
            checked(self.lib.rknn_outputs_release(self.context, 9, outputs))
        ended = time.monotonic()
        return dict(boxes=boxes, raw_person_proposals=len(proposals),
                    preprocess_ms=(prepared-begin)*1000, inference_ms=(invoked-prepared)*1000,
                    postprocess_ms=(ended-invoked)*1000, total_ms=(ended-begin)*1000)


def main(protocol):
    from person_rknn import main as run_protocol
    return run_protocol(protocol, detector_factory=Detector,
                        model_name='person_detection_v8.rknn', backend='rknn-v8', model_sha=MODEL_SHA)
