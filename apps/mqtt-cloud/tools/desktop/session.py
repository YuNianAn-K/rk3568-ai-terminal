"""Own one manual web/SSH session. Read credentials only from stdin."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import queue
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
LOCAL = ROOT / 'local/mqtt/manual'
REMOTE = '/opt/rk3568-mqtt-status-20261013'
AGENT_HASH = 'eb6d77cf5f2accd6d5bf3ea78ccc5515a9d750b18abccaf106d4cac6dbf1a1af'
PROTOCOL_HASH = '9d6a0aed9cd55272d4fee1ad7b7e93e25b51f78805a0ed15cb911718cd5be0e8'

REMOTE_CODE = r'''
import fcntl, hashlib, json, os, platform, select, signal, subprocess, sys, time
from pathlib import Path
directory=Path('/opt/rk3568-mqtt-status-20261013')
expected={'status_agent.py':'AGENT_HASH','status_protocol.py':'PROTOCOL_HASH','ca.crt':'5d550643b6400d4341550a9b14aedd0b4fac33ae5deb7d8247b6b4f799c13306'}
if platform.node()!='ATK-DLRK3568' or platform.machine()!='aarch64':sys.exit(10)
for name,digest in expected.items():
 if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:sys.exit(11)
lock=open('/tmp/rk3568-mqtt-manual.lock','a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:sys.exit(12)
for entry in Path('/proc').iterdir():
 if not entry.name.isdigit():continue
 try:
  args=(entry/'cmdline').read_bytes().split(b'\0')
  if b'status_agent.py' in args and (entry/'cwd').resolve()==directory:sys.exit(12)
 except (OSError,PermissionError):pass
settings=json.loads(sys.stdin.readline())
env=os.environ.copy();env['MQTT_PASSWORD']=settings.pop('password');env['PYTHONDONTWRITEBYTECODE']='1';settings=None
child=None;stopping=False
def stop(signum,frame):
 global stopping
 stopping=True
for sig in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(sig,stop)
try:
 child=subprocess.Popen(['python3','-u','status_agent.py','--config','config.local.json','--deps-dir','./deps'],cwd=directory,env=env,stdin=subprocess.DEVNULL)
 print(json.dumps({'agent_pid':child.pid}),flush=True)
 deadline=time.monotonic()+28800;lease=time.monotonic()+40
 while not stopping and time.monotonic()<deadline and time.monotonic()<lease and child.poll() is None:
  readable,_,_=select.select([sys.stdin],[],[],0.5)
  if readable:
   line=sys.stdin.readline()
   if not line or json.loads(line).get('action')=='stop':break
   lease=time.monotonic()+40
finally:
 if child and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=6)
  except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)
 env.pop('MQTT_PASSWORD',None)
 lock.close()
'''.replace('AGENT_HASH', AGENT_HASH).replace('PROTOCOL_HASH', PROTOCOL_HASH)


def validate_ip(value):
    address = ipaddress.IPv4Address(value)
    if (not address.is_private or address.is_loopback or address.is_multicast
            or address.is_unspecified or address.is_link_local or value.endswith('.255')):
        raise ValueError('private host IPv4 required')
    return str(address)


def load_runtime():
    runtime = json.loads((LOCAL / 'runtime.json').read_text(encoding='utf-8-sig'))
    for name in ('python', 'node', 'ssh'):
        if not Path(runtime[name]).is_file():
            raise ValueError('missing runtime')
    if not (ROOT / 'local/pan-ssh-known-hosts').is_file():
        raise ValueError('trusted SSH hosts missing')
    if not (ROOT / 'apps/mqtt-cloud/mobile-web/dist/index.html').is_file():
        raise ValueError('web files missing')
    return runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', help='public session identifier; no credentials in arguments')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    runtime = load_runtime()
    if args.check:
        print('Runtime and trusted-host files available; no network or agent started.')
        return 0
    if not args.session or len(args.session) != 32 or any(c not in '0123456789abcdef' for c in args.session):
        raise ValueError('invalid session identifier')
    state_path = LOCAL / (args.session + '.json')
    state = {'stage': 'starting', 'worker_pid': os.getpid()}
    def save(stage, text):
        state.update(stage=stage, message=text)
        temp = state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(state_path)
    save('starting', '正在核对地址与启动环境。')
    node = ssh = None
    events = queue.Queue()
    try:
        settings = json.loads(sys.stdin.readline())
        board = validate_ip(settings['ip'])
        password = settings.pop('password')
        settings = None
        if not password:
            raise ValueError('missing password')
        # Reject occupied ports, never adopt or terminate someone else's server.
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1', 8787)) == 0:
                save('failed', '8787 端口已被占用；请关闭已有网页服务后重试。')
                return 2
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((board, 9))
            state['phone_url'] = f'http://{route.getsockname()[0]}:8787/'
        stdout = (LOCAL / (args.session + '-web.log')).open('w', encoding='utf-8')
        stderr = (LOCAL / (args.session + '-web-error.log')).open('w', encoding='utf-8')
        try:
            node = subprocess.Popen([runtime['node'], 'server.mjs'], cwd=ROOT / 'apps/mqtt-cloud/mobile-web',
                                    stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        finally:
            stdout.close(); stderr.close()
        state['web_pid'] = node.pid
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if node.poll() is not None:
                raise RuntimeError('web startup failed')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8787/', timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError('web unavailable')
        ssh_args = [runtime['ssh'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                    '-o', 'ConnectionAttempts=1', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'HostKeyAlias=10.176.237.235', '-o',
                    'UserKnownHostsFile=' + str(ROOT / 'local/pan-ssh-known-hosts'),
                    'root@' + board, 'python3 -u -c ' + shlex.quote(REMOTE_CODE)]
        ssh = subprocess.Popen(ssh_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, encoding='utf-8', text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        ssh.stdin.write(json.dumps({'password': password}) + '\n'); ssh.stdin.flush()
        password = None
        def remote_reader():
            for line in ssh.stdout:
                if line.strip() == 'Status agent ready (read-only)':
                    events.put(('ready', None))
                elif line.startswith('{'):
                    try:
                        value = json.loads(line)
                        if type(value.get('agent_pid')) is int:
                            events.put(('pid', value['agent_pid']))
                    except ValueError:
                        pass
            events.put(('remote_exit', None))
        def input_reader():
            for line in sys.stdin:
                try:
                    if json.loads(line).get('action') == 'stop':
                        break
                except ValueError:
                    break
            events.put(('stop', None))
        threading.Thread(target=remote_reader, daemon=True).start()
        threading.Thread(target=input_reader, daemon=True).start()
        save('starting', '网页已启动，正在连接板端和云端。')
        deadline = time.monotonic() + 30
        heartbeat_at = 0
        ready = False
        while True:
            if node.poll() is not None:
                raise RuntimeError('web exited')
            if time.monotonic() >= heartbeat_at:
                ssh.stdin.write('{"action":"heartbeat"}\n'); ssh.stdin.flush()
                heartbeat_at = time.monotonic() + 5
            if not ready and time.monotonic() > deadline:
                save('failed', '板端连接超时；请检查当前 IP、网络和设备 MQTT 密码。')
                return 2
            try:
                kind, value = events.get(timeout=0.3)
            except queue.Empty:
                continue
            if kind == 'stop':
                save('stopping', '正在正常停止本次代理和网页。')
                break
            if kind == 'pid':
                state['agent_pid'] = value
            elif kind == 'ready':
                ready = True
                save('ready', '板端代理已连接。手机打开下方地址，用 phone-owner 查询。')
            elif kind == 'remote_exit':
                code = ssh.wait(timeout=2)
                messages = {10: '板端身份不匹配。', 11: '板端已部署文件版本不匹配。',
                            12: '已有板端代理在运行；未覆盖或终止它。'}
                save('failed', messages.get(code, '板端会话已结束；请核对 IP、可信 SSH、密码及云端权限。'))
                return 2
    except (OSError, ValueError, RuntimeError, KeyError):
        save('failed', '启动未完成；请检查本机运行路径、网络和板端配置。密码未写入日志。')
        return 2
    finally:
        remote_stopped = True
        if ssh and ssh.poll() is None:
            try:
                ssh.stdin.write('{"action":"stop"}\n'); ssh.stdin.flush(); ssh.stdin.close()
                ssh.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                remote_stopped = False
                ssh.kill(); ssh.wait(timeout=3)
        if node and node.poll() is None:
            node.terminate(); node.wait(timeout=5)
        if state['stage'] != 'failed':
            save('stopped' if remote_stopped else 'failed',
                 '本次网页和代理已停止。' if remote_stopped else '网页已停止，远程退出未确认；请检查板端代理。')
    return 0


if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError):
        print('Local launcher configuration unavailable; no credentials logged.', file=sys.stderr)
        sys.exit(2)
