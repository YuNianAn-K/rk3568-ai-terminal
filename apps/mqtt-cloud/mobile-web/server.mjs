import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
const root = new URL('./dist/', import.meta.url);
const configPath = new URL('../../../local/mobile-web/connection.json', import.meta.url);
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/protocol.js', ['protocol.js', 'text/javascript; charset=utf-8']],
  ['/vendor/mqtt.min.js', ['vendor/mqtt.min.js', 'text/javascript; charset=utf-8']]
]);
const port = Number(process.env.PORT || 8787);
const ips = Object.values(os.networkInterfaces()).flat().filter(x => x?.family === 'IPv4' && !x.internal).map(x => x.address);
const allowedHosts = new Set(['localhost', '127.0.0.1', ...ips]);
const server = http.createServer(async (request, response) => {
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Referrer-Policy', 'no-referrer');
  response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' wss:; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
  let url;
  try { url = new URL(request.url, `http://${request.headers.host}`); } catch { response.writeHead(400).end(); return; }
  if (!allowedHosts.has(url.hostname)) { response.writeHead(403).end(); return; }
  if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
  try {
    if (url.pathname === '/connection.json') {
      let config = {};
      try { config = JSON.parse(await readFile(configPath, 'utf8')); } catch { }
      const safe = { broker: process.env.MQTT_WS_URL || config.broker || '', username: process.env.MQTT_USERNAME || config.username || '' };
      response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(request.method === 'HEAD' ? '' : JSON.stringify(safe)); return;
    }
    const file = files.get(url.pathname);
    if (!file) { response.writeHead(404).end(); return; }
    const content = await readFile(new URL(file[0], root));
    response.writeHead(200, { 'Content-Type': file[1] });
    response.end(request.method === 'HEAD' ? undefined : content);
  } catch { response.writeHead(500).end('Unable to serve page'); }
});
server.listen(port, '0.0.0.0', () => {
  console.log(`RK3568 mobile console: http://127.0.0.1:${port}`);
  for (const ip of ips) console.log(`LAN: http://${ip}:${port}`);
});
