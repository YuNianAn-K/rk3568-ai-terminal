#!/usr/bin/env python3
"""Opt-in pinned RK3568 YOLOv5 backend; consumes Qt RGB, no camera or UART.

RKNN ABI follows the vendor SDK; decoding follows its Apache-2.0 YOLO demo.
System runtime and model are checked before use; default SSD stays independent.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

class Attr(C.Structure):
    _fields_ = [('index', C.c_uint32), ('n_dims', C.c_uint32),
                ('dims', C.c_uint32 * 16), ('name', C.c_char * 256),
                ('n_elems', C.c_uint32), ('size', C.c_uint32),
                ('fmt', C.c_int), ('type', C.c_int), ('qnt_type', C.c_int),
                ('fl', C.c_int8), ('zp', C.c_int32), ('scale', C.c_float),
                ('w_stride', C.c_uint32), ('size_with_stride', C.c_uint32),
                ('pass_through', C.c_uint8), ('h_stride', C.c_uint32)]

class Counts(C.Structure):
    _fields_ = [('n_input', C.c_uint32), ('n_output', C.c_uint32)]

class Version(C.Structure):
    _fields_ = [('api_version', C.c_char * 256), ('drv_version', C.c_char * 256)]

class Input(C.Structure):
    _fields_ = [('index', C.c_uint32), ('buf', C.c_void_p), ('size', C.c_uint32),
                ('pass_through', C.c_uint8), ('type', C.c_int), ('fmt', C.c_int)]

class Output(C.Structure):
    _fields_ = [('want_float', C.c_uint8), ('is_prealloc', C.c_uint8),
                ('index', C.c_uint32), ('buf', C.c_void_p), ('size', C.c_uint32)]

def load_api():
    # Keep vendor diagnostics out of the JSON stdout protocol.
    os.environ['RKNN_LOG_LEVEL'] = '0'
    lib = C.CDLL('/usr/lib/librknnrt.so')
    definitions = {
        'rknn_init': [C.POINTER(C.c_uint64), C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p],
        'rknn_query': [C.c_uint64, C.c_int, C.c_void_p, C.c_uint32],
        'rknn_inputs_set': [C.c_uint64, C.c_uint32, C.POINTER(Input)],
        'rknn_run': [C.c_uint64, C.c_void_p],
        'rknn_outputs_get': [C.c_uint64, C.c_uint32, C.POINTER(Output), C.c_void_p],
        'rknn_outputs_release': [C.c_uint64, C.c_uint32, C.POINTER(Output)],
        'rknn_destroy': [C.c_uint64]}
    for name, arguments in definitions.items():
        fn = getattr(lib, name); fn.argtypes = arguments; fn.restype = C.c_int
    return lib

def checked(code):
    if code != 0:
        raise RuntimeError('RKNN returned %d' % code)

def query(lib, context, command, record):
    checked(lib.rknn_query(context, command, C.byref(record), C.sizeof(record)))
    return record

def attr_dict(attr):
    return dict(index=attr.index, dims=list(attr.dims)[:attr.n_dims],
                name=attr.name.decode(), n_elems=attr.n_elems, size=attr.size,
                fmt=attr.fmt, type=attr.type, qnt_type=attr.qnt_type,
                zp=attr.zp, scale=attr.scale)

MODEL_SHA='544bdbe8b26a86f065b4479a4eeff5541a68a7366205f5e55f1069218108d398'
ANCHORS=(((10,13),(16,30),(33,23)),((30,61),(62,45),(59,119)),((116,90),(156,198),(373,326)))

def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -80, 80)))

def decode_head(array, attr, anchors, threshold=.4):
    # The vendor model exports logits, not probabilities.
    grid=640//(8 * 2**attr.index)
    if array.shape != (255,grid,grid) or array.dtype != np.int8:
        raise ValueError('unexpected YOLO head shape/dtype')
    if not np.isfinite(attr.scale) or attr.scale <= 0:
        raise ValueError('invalid output quantization')
    q=array.reshape(3,85,grid,grid)
    objectness=sigmoid((q[:,4].astype(np.float32)-attr.zp)*attr.scale)
    person=sigmoid((q[:,5].astype(np.float32)-attr.zp)*attr.scale)
    scores=objectness*person
    # Keep person only when it wins the full COCO class comparison.
    keep=(scores>=threshold) & (q[:,5] == q[:,5:].max(axis=1))
    anchor,y,x=np.nonzero(keep)
    if not len(anchor): return []
    coords=(q[anchor,:4,y,x].astype(np.float32)-attr.zp)*attr.scale
    coords=sigmoid(coords)
    stride=640/grid
    cx=(coords[:,0]*2-.5+x)*stride
    cy=(coords[:,1]*2-.5+y)*stride
    width=(coords[:,2]*2)**2*np.array(anchors)[anchor,0]
    height=(coords[:,3]*2)**2*np.array(anchors)[anchor,1]
    result=[]
    for a,b,w,h,score in zip(cx,cy,width,height,scores[anchor,y,x]):
        left,top=max(0.,float(a-w/2)/640),max(0.,float(b-h/2)/640)
        right,bottom=min(1.,float(a+w/2)/640),min(1.,float(b+h/2)/640)
        if right>left and bottom>top:
            result.append(dict(left=left,top=top,right=right,bottom=bottom,score=float(score)))
    return result

def nms(boxes, threshold=.45):
    result=[]
    for box in sorted(boxes,key=lambda b:b['score'],reverse=True):
        area=(box['right']-box['left'])*(box['bottom']-box['top'])
        duplicate=False
        for other in result:
            intersection=max(0,min(box['right'],other['right'])-max(box['left'],other['left']))*max(0,min(box['bottom'],other['bottom'])-max(box['top'],other['top']))
            other_area=(other['right']-other['left'])*(other['bottom']-other['top'])
            if intersection/(area+other_area-intersection) > threshold:
                duplicate=True;break
        if not duplicate:
            result.append(box)
            if len(result)==10: break
    return result[:10]

class Detector:
    def __init__(self, model):
        data=Path(model).read_bytes()
        if hashlib.sha256(data).hexdigest()!=MODEL_SHA:
            raise ValueError('NPU model checksum mismatch')
        self.lib,self.context=load_api(),C.c_uint64()
        buffer=C.create_string_buffer(data)
        checked(self.lib.rknn_init(C.byref(self.context),buffer,len(data),0,None))
        try:
            self.version=query(self.lib,self.context,5,Version())
            if not self.version.api_version.decode().startswith('1.5.2 ') or self.version.drv_version.decode()!='0.9.2':
                raise ValueError('unverified RKNN runtime/driver version')
            counts=query(self.lib,self.context,0,Counts())
            if (counts.n_input,counts.n_output)!=(1,3): raise ValueError('unexpected IO count')
            inp=query(self.lib,self.context,1,Attr(index=0))
            if list(inp.dims)[:inp.n_dims]!=[1,640,640,3] or inp.fmt!=1:
                raise ValueError('unexpected NPU input shape/format')
            self.attrs=[query(self.lib,self.context,2,Attr(index=i)) for i in range(3)]
            for a,g in zip(self.attrs,(80,40,20)):
                if (list(a.dims)[:a.n_dims]!=[1,255,g,g] or a.type!=2 or a.fmt!=0 or a.qnt_type!=2 or a.size!=255*g*g or a.n_elems!=a.size or not np.isfinite(a.scale) or a.scale<=0):
                    raise ValueError('unexpected NPU output contract')
        except Exception:
            self.close();raise

    def close(self):
        if self.context.value:
            checked(self.lib.rknn_destroy(self.context));self.context.value=0

    def detect(self,rgb):
        if rgb.shape!=(480,640,3) or rgb.dtype!=np.uint8:
            raise ValueError('unexpected RGB frame')
        begin=time.monotonic()
        # Direct resize matches this pinned vendor demo's imresize/scales.
        import cv2
        image=cv2.resize(rgb,(640,640),interpolation=cv2.INTER_LINEAR)
        inp=Input(index=0,buf=image.ctypes.data,size=image.nbytes,type=3,fmt=1)
        checked(self.lib.rknn_inputs_set(self.context,1,C.byref(inp)))
        prepared=time.monotonic()
        checked(self.lib.rknn_run(self.context,None))
        outputs=(Output*3)(*[Output(index=i) for i in range(3)])
        checked(self.lib.rknn_outputs_get(self.context,3,outputs,None))
        invoked=time.monotonic()
        try:
            candidates=[]
            for out,attr,anchors in zip(outputs,self.attrs,ANCHORS):
                if not out.buf or out.size!=attr.size: raise ValueError('unexpected NPU output buffer')
                values=np.ctypeslib.as_array(C.cast(out.buf,C.POINTER(C.c_int8)),shape=(attr.n_elems,))
                candidates.extend(decode_head(values.reshape(tuple(attr.dims)[1:attr.n_dims]),attr,anchors))
            boxes=nms(candidates)
        finally:
            checked(self.lib.rknn_outputs_release(self.context,3,outputs))
        ended=time.monotonic()
        return dict(boxes=boxes,raw_person_proposals=len(candidates),
                    preprocess_ms=(prepared-begin)*1000,inference_ms=(invoked-prepared)*1000,
                    postprocess_ms=(ended-invoked)*1000,total_ms=(ended-begin)*1000)


def main(protocol, detector_factory=Detector, model_name='person_detection.rknn',
         backend='rknn', model_sha=MODEL_SHA):
    import cv2
    cv2.setNumThreads(1)
    started=time.monotonic()
    detector=detector_factory(Path(__file__).with_name(model_name))
    capture=None
    try:
        protocol.emit(dict(event='ready',backend=backend,model_sha256=model_sha,person_class=0,
            api=detector.version.api_version.decode(),driver=detector.version.drv_version.decode(),
            startup_ms=round((time.monotonic()-started)*1000,3),rss_kib=protocol.rss_kib()))
        if os.environ.get('PERSON_CAPTURE_DIR'):
            try:
                from person_capture import DiagnosticCapture
                capture=DiagnosticCapture(os.environ['PERSON_CAPTURE_DIR'])
                print('PERSON_CAPTURE_READY '+str(capture.directory),file=sys.stderr,flush=True)
            except Exception as error:
                print('PERSON_CAPTURE_ERROR '+str(error),file=sys.stderr,flush=True)
        candidate_filter=protocol.CandidateFilter()
        previous_wall,previous_cpu=time.monotonic(),time.process_time()
        seq=0
        while True:
            raw=protocol.read_frame(sys.stdin.buffer)
            if raw is None: return
            begin=time.monotonic()
            rgb=np.frombuffer(raw,dtype=np.uint8).reshape(480,640,3)
            result=detector.detect(rgb)
            candidates=protocol.suppress_duplicates(result['boxes'])
            people=candidate_filter.update(candidates)
            finished,cpu=time.monotonic(),time.process_time()
            seq+=1
            protocol.emit(dict(event='result',seq=seq,boxes=people,candidate_count=len(candidates),
                raw_person_proposals=result['raw_person_proposals'],
                preprocess_ms=round(result['preprocess_ms'],3),inference_ms=round(result['inference_ms'],3),
                postprocess_ms=round(result['postprocess_ms'],3),detector_total_ms=round((finished-begin)*1000,3),
                worker_cpu_one_core_pct=round(100*(cpu-previous_cpu)/max(.001,finished-previous_wall),2),
                worker_rss_kib=protocol.rss_kib()))
            if capture:
                # YOLO proposals are reduced by model NMS before geometric
                # fragment filtering; raw_boxes refers to those model results.
                capture.observe(raw,dict(seq=seq,backend=backend,model_sha256=model_sha,
                    raw_boxes=result['boxes'],candidates=candidates,boxes=people,
                    inference_ms=round(result['inference_ms'],3)))
                if capture.error:
                    print('PERSON_CAPTURE_ERROR '+capture.error,file=sys.stderr,flush=True)
                    capture.close();capture=None
            previous_wall,previous_cpu=finished,cpu
    finally:
        if capture:
            error=capture.close()
            print('PERSON_CAPTURE_END '+json.dumps(dict(count=capture.count,error=error)),file=sys.stderr,flush=True)
        detector.close()

