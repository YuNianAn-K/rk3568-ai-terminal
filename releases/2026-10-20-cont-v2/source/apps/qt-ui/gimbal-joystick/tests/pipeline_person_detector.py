"""Test fixture only; install beside tracker tests, never in candidate app."""
import json,os,struct,sys,time
mode=os.environ.get('PERSON_TEST_MODE','pipeline')
if mode=='crash':sys.exit(5)
print(json.dumps(dict(event='ready')),flush=True);seq=0
while True:
    header=sys.stdin.buffer.read(4)
    if not header:break
    assert len(header)==4
    length=struct.unpack('<I',header)[0];raw=sys.stdin.buffer.read(length)
    assert length==640*480*3 and len(raw)==length and raw[0]==255 and raw[2]==0
    if os.environ.get('PERSON_TEST_AUDIT'):
        with open(os.environ['PERSON_TEST_AUDIT'],'a') as f:f.write(json.dumps(dict(id=raw[1],time=time.monotonic()))+'\n')
    delay=1.1 if mode=='late' else float(os.environ.get('PERSON_TEST_DELAY','.18')) if mode=='pipeline' else .12
    time.sleep(delay);seq+=1
    print(json.dumps(dict(event='result',seq=seq+(10 if mode=='bad_seq' else 0),boxes=[dict(left=.1+raw[1]/1000,top=.2,right=.4,bottom=.8,score=.9)],inference_ms=delay*1000)),flush=True)
