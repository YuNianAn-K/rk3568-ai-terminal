"""Pinned RK3568 YOLOv8 backend; Qt RGB input only, no camera or UART.

DFL decoding follows the Rockchip model-zoo export and Apache-2.0 demo.
"""
import numpy as np
import ctypes as C
import hashlib
from pathlib import Path
import time
import math
from person_rknn import Attr, Counts, Input, Output, Version, checked, load_api, query

MODEL_SHA = '36566148f41a51ba192ca44423e32238223d3a77e9fe11e8618c2b5d0c0c6ecd'
REFINER_SHA = '7702e02808a4f977cd9ba9a6d2ed7da2d1eaaae376b7162a149824bc5928be29'

def reference_shape(a,b):
    intersection=max(0.,min(a['right'],b['right'])-max(a['left'],b['left']))*max(0.,min(a['bottom'],b['bottom'])-max(a['top'],b['top']))
    area=(a['right']-a['left'])*(a['bottom']-a['top'])
    other=(b['right']-b['left'])*(b['bottom']-b['top'])
    return intersection/(area+other-intersection),min(area,other)/max(area,other)



def decode(outputs, threshold=.4):
    if len(outputs) not in (6, 9):
        raise ValueError('unexpected YOLOv8 output count')
    proposals = []
    per_branch = len(outputs) // 3
    for branch, grid in enumerate((80, 40, 20)):
        position, classes = outputs[branch*per_branch:branch*per_branch+2]
        if position.shape != (1, 64, grid, grid) or classes.shape != (1, 80, grid, grid):
            raise ValueError('unexpected DFL/class contract')
        # Min/max already inspect every class value. Nonfinite extrema reject
        # NaN/Inf without allocating another full class-sized finite mask.
        class_min, class_max = classes.min(), classes.max()
        if (not np.isfinite(position).all() or
                not np.isfinite(class_min) or not np.isfinite(class_max)):
            raise ValueError('nonfinite model output')
        # Rockchip export applies Sigmoid to classes; DFL remains logits.
        if class_min < -.01 or class_max > 1.01:
            raise ValueError('class output is not probability')
        scores = classes[0, 0]
        # Below-threshold locations cannot produce a person proposal. Keep
        # the full tensor validation above, then compare all COCO classes only
        # at eligible locations. Argmax keeps class-0 tie behavior and row order.
        y, x = np.nonzero(scores >= threshold)
        if len(y):
            winners = classes[0][:, y, x].argmax(axis=0) == 0
            y, x = y[winners], x[winners]
        if not len(y):
            continue
        logits = position[0, :, y, x].reshape(-1, 4, 16)
        weights = np.exp(logits-logits.max(axis=2, keepdims=True))
        distances = (weights*np.arange(16)).sum(axis=2)/weights.sum(axis=2)
        stride = 640/grid
        # Batch the same float64 coordinate arithmetic, retaining branch/grid
        # order. Validation, class ties, clipping and NMS remain unchanged.
        left = np.maximum(0., (x+.5-distances[:, 0])*stride/640)
        top = np.maximum(0., ((y+.5-distances[:, 1])*stride-80)/480)
        right = np.minimum(1., (x+.5+distances[:, 2])*stride/640)
        bottom = np.minimum(1., ((y+.5+distances[:, 3])*stride-80)/480)
        valid = (right > left) & (bottom > top)
        coordinates = np.column_stack((left[valid], top[valid], right[valid],
                                       bottom[valid], scores[y, x][valid]))
        for row in coordinates.tolist():
            proposals.append(dict(zip(('left', 'top', 'right', 'bottom', 'score'), row)))
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
    def __init__(self, model, expected_sha=MODEL_SHA, refine=True):
        self.refiner = None
        self.reference = None
        self.reference_hits = 0
        data = Path(model).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
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
            if refine:
                self.refiner = Detector(Path(model).with_name('person_detection_v8s.rknn'),
                                        expected_sha=REFINER_SHA, refine=False)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.refiner is not None:
            self.refiner.close()
            self.refiner = None
        if self.context.value:
            checked(self.lib.rknn_destroy(self.context))
            self.context.value = 0

    def _detect_primary(self, rgb):
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

    def detect(self, rgb):
        started = time.monotonic()
        primary = self._detect_primary(rgb)
        boxes = primary['boxes']
        if self.refiner is None:
            return primary
        if len(boxes)>1:
            self.reference = None
            self.reference_hits = 0
            primary['refine_used'] = False
            return primary
        if boxes and boxes[0]['score']>=.70:
            self._remember_reference(boxes[0], started)
            primary['refine_used'] = False
            return primary
        # A missing body can use a recent unique real observation for matching,
        # never as an output box. Its original age is not refreshed by misses.
        reference = boxes[0] if boxes else (
            self.reference[0] if self.reference and time.monotonic()-self.reference[1]<=.50 else None)
        if reference is None:
            primary['refine_used'] = False
            return primary
        extra = self.refiner.detect(rgb)
        candidate = extra['boxes'][0] if len(extra['boxes'])==1 else None
        # A second auxiliary observation must not discard a uniquely matching
        # mature body on an otherwise empty primary frame. Keep ALL current
        # auxiliary boxes so downstream ambiguity handling still sees rivals.
        if not boxes and len(extra['boxes'])>1 and self.reference and \
                self.reference_hits>=3 and time.monotonic()-self.reference[1]<=.50:
            ranked=[]
            for observed in extra['boxes']:
                if observed['score']<.40: continue
                iou,scale=reference_shape(self.reference[0],observed)
                ranked.append((iou,scale,observed))
            ranked.sort(key=lambda row:row[0],reverse=True)
            if ranked and ranked[0][0]>=.65 and ranked[0][1]>=.65 and \
                    (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.20):
                candidate=ranked[0][2]
        continuation = False
        if candidate is not None and candidate['score']>=.40 and self.reference and \
                getattr(self,'reference_hits',0)>=3 and time.monotonic()-self.reference[1]<=.50:
            iou,scale=reference_shape(self.reference[0],candidate)
            continuation = iou>=.50 and scale>=.50
        use = candidate is not None and candidate['score']>=max(.55, (boxes[0]['score']+.08) if boxes else .55)
        if not boxes and self.reference and time.monotonic()-self.reference[1]>.50:
            use=False
            continuation=False
        if use and not continuation:
            a,b=reference,candidate
            intersection=max(0.,min(a['right'],b['right'])-max(a['left'],b['left']))*max(0.,min(a['bottom'],b['bottom'])-max(a['top'],b['top']))
            area=(a['right']-a['left'])*(a['bottom']-a['top'])
            other=(b['right']-b['left'])*(b['bottom']-b['top'])
            distance=math.sqrt(((a['left']+a['right']-b['left']-b['right'])/2)**2+((a['top']+a['bottom']-b['top']-b['bottom'])/2)**2)
            use = intersection/area>=.60 and distance<=.35 if boxes else (
                intersection/(area+other-intersection)>=.25 and min(area,other)/max(area,other)>=.40 and distance<=.25)
        use = bool(use or continuation)
        chosen = dict(extra if use else primary)
        for name in ['preprocess_ms','inference_ms','postprocess_ms']:
            chosen[name]=primary[name]+extra[name]
        chosen['total_ms']=(time.monotonic()-started)*1000
        chosen['refine_used']=bool(use)
        chosen['refine_continuity']=bool(continuation)
        chosen['refine_attempted']=True
        if use:
            self._remember_reference(candidate, started)
        return chosen

    def _remember_reference(self, box, stamp):
        previous=self.reference
        same=previous and 0<=stamp-previous[1]<=.50 and reference_shape(previous[0],box)[0]>=.50
        self.reference_hits=getattr(self,'reference_hits',0)+1 if same else 1
        self.reference=(box,stamp)


def main(protocol):
    from person_rknn import main as run_protocol
    return run_protocol(protocol, detector_factory=Detector,
                        model_name='person_detection_v8.rknn', backend='rknn-v8', model_sha=MODEL_SHA)
