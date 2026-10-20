"""YuNet 2023 decoder from documented OpenCV formulas; no DFL or devices."""
import numpy as np

OUTPUTS=[f'{kind}_{stride}' for kind in ('cls','obj','bbox','kps') for stride in (8,16,32)]

def preprocess(rgb):
    import cv2
    assert rgb.shape==(480,640,3) and rgb.dtype==np.uint8
    bgr=np.zeros((320,320,3),np.uint8)
    bgr[40:280]=cv2.resize(rgb[:,:,::-1],(320,240),interpolation=cv2.INTER_LINEAR)
    return bgr

def decode(outputs,threshold=.80,nms=.30):
    faces=[]
    for stride in (8,16,32):
        width=320//stride;n=width*width
        cls=np.asarray(outputs[f'cls_{stride}'],np.float32).reshape(n)
        obj=np.asarray(outputs[f'obj_{stride}'],np.float32).reshape(n)
        bbox=np.asarray(outputs[f'bbox_{stride}'],np.float32).reshape(n,4)
        points=np.asarray(outputs[f'kps_{stride}'],np.float32).reshape(n,5,2)
        scores=np.sqrt(np.clip(cls,0,1)*np.clip(obj,0,1))
        for index in np.flatnonzero(scores>np.float32(threshold)):
            r,c=divmod(int(index),width)
            center=(bbox[index,:2]+np.asarray([c,r],np.float32))*stride
            wh=np.exp(bbox[index,2:])*stride
            p=(points[index]+np.asarray([c,r],np.float32))*stride
            faces.append(np.concatenate((center-wh/2,wh,p.reshape(-1),[scores[index]])).astype(np.float32))
    if not faces:return np.empty((0,15),np.float32)
    faces=np.stack(faces)
    # OpenCV FaceDetectorYN uses truncated Rect2i for NMS, float boxes for output.
    rect=np.trunc(faces[:,:4]).astype(np.int64)
    order=np.argsort(-faces[:,14],kind='stable')[:5000]
    keep=[]
    for i in order:
        a=rect[i];area=max(0,a[2])*max(0,a[3])
        for j in keep:
            b=rect[j]
            intersection=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))*max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
            union=area+max(0,b[2])*max(0,b[3])-intersection
            if union>0 and intersection/union>nms:break
        else:keep.append(i)
    return faces[keep]

def to_original(faces):
    result=[]
    for face in faces:
        x,y,w,h=map(float,face[:4])
        box=[2*x,2*(y-40),2*(x+w),2*(y+h-40)]
        if not (0<=sum(box[::2])/2<=640 and 0<=sum(box[1::2])/2<=480):continue
        result.append(dict(xyxy=box,landmarks=[[2*float(face[k]),2*(float(face[k+1])-40)] for k in range(4,14,2)],score=float(face[14])))
    return result
