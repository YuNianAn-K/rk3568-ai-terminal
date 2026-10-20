const el = id => document.getElementById(id);
const session = new URLSearchParams(location.hash.slice(1)).get('session') || '';
const headers = { 'X-Monitor-Session': session, 'Content-Type': 'application/json' };
let stopped = false;
let refreshing = false;
const number = (v, places = 4) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(places) : '—';
const stamp = value => value ? new Date(value * 1000).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'}) : '未更新';
const rate = value => value === null || value === undefined ? '—' : `${number(value / 1000, 2)} Kbps`;
function render(data) {
  el('month').textContent = data.month;
  el('status').textContent = data.message;
  el('credential-status').textContent = data.credential_notice || (data.credential_saved ? '凭据已由Windows加密保存 · 下次启动自动连接' : '尚未保存凭据；可选择加密记住，下次自动连接。');
  el('forget').hidden = !data.credential_saved;
  el('credentials').textContent = data.credential_saved ? '更换只读凭据' : '接入只读凭据';
  const metrics = data.metrics;
  el('in').textContent = rate(metrics?.in.bps);
  el('out').textContent = rate(metrics?.out.bps);
  const used = metrics?.out.month_gb ?? null;
  el('used').textContent = number(used);
  el('bar').value = used ?? 0;
  const labels = { unknown:'尚未获取实时数据', normal:'已观测量低于10GB', notice:'已达10GB · 注意用量', warning:'已达15GB · 接近额度', critical:'已达18GB · 请处理', over:'已观测量达到20GB' };
  el('level').textContent = labels[data.quota_estimate.level] + (data.metrics_stale && used !== null ? '（旧值）' : '');
  el('coverage').textContent = metrics ? `监控样本覆盖 ${number(metrics.out.covered_seconds / 3600, 1)} 小时；缺失区间未知。单实例估算，不是账号准确余量。` : '等待只读接入；不将未知流量显示为零。';
  el('today').textContent = metrics ? `${number(metrics.in.day_gb)} / ${number(metrics.out.day_gb)} GB` : '—';
  el('bill').textContent = data.bill?.cny !== null && data.bill?.cny !== undefined ? `¥ ${number(data.bill.cny, 2)}` : '待出账 / 未知';
  el('bill-note').textContent = data.bill_error || data.bill?.status || '未查询不代表费用为零';
  el('updated').textContent = `监控：${stamp(data.metrics_at)} ｜账单：${stamp(data.bill_at)}`;
  el('observation').textContent = data.observation ? `${data.observation.date} 控制台核验：ECS已升级CDT，深圳当月出网 ${number(data.observation.used_gb)} GB；账单暂无记录。这是历史记录，不会自动当成实时余额。` : '没有本月核验记录，旧月份记录已失效。';
  document.title = `${used === null ? '待接入' : number(used) + 'GB'} · ECS 流量与费用`;
}
async function refresh() {
  if (refreshing || stopped) return;
  refreshing = true;
  try {
    const response = await fetch('/api/state', {headers, cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error();
    render(await response.json());
  } catch {
    el('status').textContent = '本机监控未连接或会话已过期，请重新启动入口。旧数值不能代表当前状态。';
    el('in').textContent = el('out').textContent = '—';
  } finally { refreshing = false; }
}
async function post(path, data = {}) {
  const response = await fetch(path, {method:'POST', headers, body:JSON.stringify(data), signal:AbortSignal.timeout(10000)});
  if (!response.ok) throw new Error();
}
el('refresh').onclick = refresh;
el('credentials').onclick = () => {el('connect-error').textContent=''; el('connect').showModal();};
function updateSaveChoice() {
  const temporary = !!el('token').value.trim();
  el('save-connect').disabled = temporary;
  el('save-note').textContent = temporary ? '临时STS令牌会到期，仅支持“仅本次连接”。长期自动连接请使用专用RAM AccessKey。' : '保存后仅当前Windows用户可解锁；以后双击桌面入口即可自动连接。';
}
el('token').oninput = updateSaveChoice;
function clearFields() { ['access-id','secret','token'].forEach(id => {el(id).value='';}); updateSaveChoice(); }
el('cancel').onclick = () => {clearFields(); el('connect').close();};
el('connect').addEventListener('cancel', clearFields);
el('connect-form').onsubmit = async event => {
  event.preventDefault();
  const data = { access_id:el('access-id').value.trim(), secret:el('secret').value.trim(), token:el('token').value.trim(), remember:event.submitter?.id === 'save-connect' };
  el('save-connect').disabled = el('once-connect').disabled = true;
  try { await post('/api/connect', data); clearFields(); el('connect-error').textContent=''; el('connect').close(); await refresh(); }
  catch {el('connect-error').textContent='接入未完成：请检查字段或本机加密存储权限。未自动降级为明文保存。';}
  finally {data.access_id=data.secret=data.token=''; el('once-connect').disabled=false; updateSaveChoice();}
};
el('forget').onclick = async () => {
  try {await post('/api/forget'); await refresh();}
  catch {el('status').textContent='忘记凭据失败，请重新启动监控后重试；尚未确认删除。';}
};
el('stop').onclick = async () => {
  try {await post('/api/stop'); stopped=true; el('status').textContent='已停止本机监控，云端服务不受影响；可关闭此窗口。'; el('in').textContent=el('out').textContent='—';}
  catch {el('status').textContent='无法联系本机监控；关闭页面后，采集程序将在无连接120秒后退出。';}
};
setInterval(refresh, 5000);
refresh();
