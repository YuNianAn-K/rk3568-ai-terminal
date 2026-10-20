"""Isolated same-RGB-frame v8 body plus YuNet face candidate."""
import ctypes as C
import hashlib
from pathlib import Path
import time
import numpy as np
from person_rknn import Attr,Counts,Input,Output,Version,checked,load_api,query
from person_rknn_v8 import Detector as BodyDetector,MODEL_SHA
from head_decode import preprocess,decode,to_original

HEAD_SHA='efaf711a5b5c1a399d02be51fe2cb7863e28c29da4e9b864dfe6f4c12c59e76a'
class HeadDetector:
    def __init__(self):
        model=Path(__file__).with_name('yunet-fixed320-fp16.rknn').read_bytes()
        assert hashlib.sha256(model).hexdigest()==HEAD_SHA
        self.lib=load_api();self.context=C.c_uint64();buffer=C.create_string_buffer(model)
        checked(self.lib.rknn_init(C.byref(self.context),buffer,len(model),0,None))
        try:
            v=query(self.lib,self.context,5,Version())
            assert v.api_version.decode().startswith('1.5.2 ') and v.drv_version.decode()=='0.9.2'
            n=query(self.lib,self.context,0,Counts());assert (n.n_input,n.n_output)==(1,12)
            a=query(self.lib,self.context,1,Attr(index=0));assert list(a.dims)[:a.n_dims]==[1,320,320,3] and a.fmt==1 and a.type==1
            self.attrs=[query(self.lib,self.context,2,Attr(index=i)) for i in range(12)]
            self.names=[f'{kind}_{stride}' for kind in ('cls','obj','bbox','kps') for stride in (8,16,32)]
            for a,name in zip(self.attrs,self.names):
                kind,stride=name.split('_');n=(320//int(stride))**2;c=10 if kind=='kps' else 4 if kind=='bbox' else 1
                assert a.name.decode()==name and list(a.dims)[:a.n_dims]==[1,n,c,1] and a.fmt==0 and a.type==1 and a.size==n*c*2
        except Exception:self.close();raise
    def close(self):
        if self.context.value:checked(self.lib.rknn_destroy(self.context));self.context.value=0
    def detect(self,rgb):
        image=preprocess(rgb)
        entry=Input(index=0,buf=image.ctypes.data,size=image.nbytes,type=3,fmt=1)
        checked(self.lib.rknn_inputs_set(self.context,1,C.byref(entry)));checked(self.lib.rknn_run(self.context,None))
        outputs=(Output*12)(*[Output(index=i,want_float=1) for i in range(12)])
        checked(self.lib.rknn_outputs_get(self.context,12,outputs,None));raw={}
        try:
            for out,a,name in zip(outputs,self.attrs,self.names):
                assert out.buf and out.size==a.n_elems*4
                v=np.ctypeslib.as_array(C.cast(out.buf,C.POINTER(C.c_float)),shape=(a.n_elems,)).copy()
                assert np.isfinite(v).all();raw[name]=v.reshape(tuple(a.dims)[:a.n_dims])[:,:,:,0]
        finally:checked(self.lib.rknn_outputs_release(self.context,12,outputs))
        faces=to_original(decode(raw))
        return [dict(x=(f['xyxy'][0]+f['xyxy'][2])/1280,y=(f['xyxy'][1]+f['xyxy'][3])/960,width=(f['xyxy'][2]-f['xyxy'][0])/640,score=f['score']) for f in faces[:10]]

class Detector(BodyDetector):
    head_sha=HEAD_SHA
    def __init__(self,model):
        self.head=None
        super().__init__(model)
        try:self.head=HeadDetector()
        except Exception:super().close();raise
    def close(self):
        if self.head:self.head.close();self.head=None
        super().close()
    def detect(self,rgb):
        start=time.monotonic();result=super().detect(rgb);body_end=time.monotonic()
        result['heads']=self.head.detect(rgb)
        result['head_ms']=(time.monotonic()-body_end)*1000
        result['joint_ms']=(time.monotonic()-start)*1000
        return result

def main(protocol):
    from person_rknn import main as run
    return run(protocol,detector_factory=Detector,model_name='person_detection_v8.rknn',backend='rknn-v8-head',model_sha=MODEL_SHA)
