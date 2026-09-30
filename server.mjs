import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDatabase, importDocuments } from './backend/db.mjs';
import { automaticBackup } from './backend/workspace.mjs';
import { createApi } from './backend/api.mjs';
import { serverOptions, lanInterfaces, createNetworkPolicy } from './backend/network.mjs';

const root = dirname(fileURLToPath(import.meta.url));
try { process.loadEnvFile(resolve(root, '.env')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
let config;
try { config = serverOptions(); }
catch (error) { console.error(error.message); process.exit(1); }
if (config.help) { console.log('Usage: node server.mjs [--lan] [--port 5173]\nDefault: this PC only. --lan: devices on connected IPv4 subnets.'); process.exit(0); }
const { port } = config;
// Local mode needs only loopback; do not require LAN enumeration permissions.
const interfaces = config.lan ? lanInterfaces() : [];
const allowRequest = createNetworkPolicy(config, interfaces);
const db = openDatabase(resolve(root, process.env.HAEDAP_DB_PATH || 'data/haedap.sqlite'));
// Seed once; subsequent starts must not replace a user's newer imported revisions.
if (!db.prepare('SELECT id FROM documents LIMIT 1').get()) importDocuments(db, JSON.parse(await readFile(resolve(root, 'knowledge/seed.json'), 'utf8')));
const backupDir=resolve(dirname(resolve(root, process.env.HAEDAP_DB_PATH || 'data/haedap.sqlite')), 'backups');
const api = createApi(db, { allowRequest, backupDir });
const autoBackupTimer=setInterval(()=>{try{automaticBackup(db,backupDir);}catch(e){console.error('Automatic backup failed:',e.message);}},60000);
autoBackupTimer.unref();
const publicFiles = new Set(['index.html', 'app.js', 'style.css', 'favicon.svg',
  'ui/api.js', 'ui/state.js', 'ui/helpers.js', 'ui/icons.js', 'ui/sample-data.js',
  'ui/extended-views.js', 'ui/forms.js', 'ui/pdf.js', 'ui/csv.js', 'ui/views.js', 'ui/operations-view.js', 'ui/report-view.js', 'ui/ui.css']);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.map': 'application/json; charset=utf-8' };

const server = http.createServer(async (req, res) => {
  const send = (status, message) => { res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end(req.method === 'HEAD' ? undefined : message); };
  if (!allowRequest(req)) return send(403, 'Use the server address printed in the terminal, from this PC or its connected network.');
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); }
  catch { return send(400, 'Bad request'); }
  if (pathname.startsWith('/api/')) return api(req, res, pathname);
  if (!['GET', 'HEAD'].includes(req.method)) { res.setHeader('Allow', 'GET, HEAD'); return send(405, 'Method not allowed'); }
  const relative = pathname === '/' ? 'index.html' : pathname.slice(1);
  if (relative.includes('\\') || relative.includes('\0') || relative.split('/').some(part => part.startsWith('.'))) return send(404, 'Not found');
  if (!publicFiles.has(relative) && !relative.startsWith('fonts/') && !relative.startsWith('vendor/leaflet/') && !relative.startsWith('vendor/pdfjs/')) return send(404, 'Not found');
  const target = resolve(root, relative);
  if (!target.startsWith(root + sep)) return send(404, 'Not found');
  try {
    if (!(await stat(target)).isFile()) return send(404, 'Not found');
    const data = await readFile(target);
    res.writeHead(200, { 'Content-Type': types[extname(target)] || 'application/octet-stream', 'Content-Length': data.length, 'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff' });
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch (error) {
    if (['ENOENT', 'ENOTDIR'].includes(error.code)) return send(404, 'Not found');
    console.error(error.message);
    send(500, 'Server error');
  }
});
server.on('error', error => {
  console.error(error.code === 'EADDRINUSE' ? `Port ${port} is in use. Stop the existing server or run with --port ${port < 65535 ? port + 1 : 5173}.` : error.message);
  clearInterval(autoBackupTimer); db.close(); process.exitCode = 1;
});
server.listen(port, config.host, () => {
  console.log(`HAEDAP: http://127.0.0.1:${port}\nMode: ${config.lan ? 'LAN' : 'Local (this PC only)'}`);
  if (config.lan) {
    for (const entry of interfaces) console.log(`LAN (${entry.name}): http://${entry.address}:${port}`);
    if (!interfaces.length) console.log('No LAN IPv4 address found. Connect Wi-Fi/Ethernet, then restart.');
    console.log('Other devices: use a LAN URL above on the same network. Reports share this PC\'s database.');
  }
  console.log('Press Ctrl+C to stop.');
});
server.requestTimeout = 35000;
server.headersTimeout = 10000;
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { clearInterval(autoBackupTimer); server.close(() => { db.close(); process.exit(0); }); });
