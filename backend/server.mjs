import http from 'node:http';
import { frontendProxy } from './frontend-proxy.mjs';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { projectRoot, databasePath } from './paths.mjs';
import { openDatabase, importDocuments } from './db.mjs';
import { automaticBackup } from './workspace.mjs';
import { createApi } from './api.mjs';
import {
  serverOptions,
  lanInterfaces,
  createNetworkPolicy,
} from './network.mjs';

const root = projectRoot;
const frontend = frontendProxy(process.env.HAEDAP_FRONTEND_ORIGIN);
try {
  process.loadEnvFile(resolve(root, '.env'));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
let config;
try {
  config = serverOptions();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
if (config.help) {
  console.log(
    'Usage: node backend/server.mjs [--lan] [--port 5173]\nDefault: this PC only. --lan: devices on connected IPv4 subnets.',
  );
  process.exit(0);
}
const { port } = config;
// Local mode needs only loopback; do not require LAN enumeration permissions.
const interfaces = config.lan ? lanInterfaces() : [];
const allowRequest = createNetworkPolicy(config, interfaces);
const dbPath = databasePath();
const db = openDatabase(dbPath);
// Seed once; subsequent starts must not replace a user's newer imported revisions.
if (!db.prepare('SELECT id FROM documents LIMIT 1').get())
  importDocuments(
    db,
    JSON.parse(
      await readFile(resolve(root, 'backend/knowledge/seed.json'), 'utf8'),
    ),
  );
const backupDir = resolve(dirname(dbPath), 'backups');
const api = createApi(db, { allowRequest, backupDir });
const autoBackupTimer = setInterval(() => {
  try {
    automaticBackup(db, backupDir);
  } catch (e) {
    console.error('Automatic backup failed:', e.message);
  }
}, 60000);
autoBackupTimer.unref();
const server = http.createServer(async (req, res) => {
  const send = (status, message) => {
    res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(req.method === 'HEAD' ? undefined : message);
  };
  if (!allowRequest(req))
    return send(
      403,
      'Use the server address printed in the terminal, from this PC or its connected network.',
    );
  let pathname;
  try {
    pathname = decodeURIComponent(
      new URL(req.url, 'http://localhost').pathname,
    );
  } catch {
    return send(400, 'Bad request');
  }
  if (pathname.startsWith('/api/')) return api(req, res, pathname);
  if (
    pathname.split('/').some((part) => part.startsWith('.')) ||
    /^\/(frontend|backend|src|data|knowledge|tests|scripts|legacy-ui|node_modules)(\/|$)/.test(
      pathname,
    ) ||
    [
      '/server.mjs',
      '/package.json',
      '/package-lock.json',
      '/next.config.mjs',
      '/AGENTS.md',
      '/README.md',
    ].includes(pathname)
  )
    return send(404, 'Not found');
  if (frontend) return frontend.request(req, res);
  if (pathname === '/')
    return send(
      503,
      'Next.js 화면 서버가 실행되지 않았습니다. npm start 또는 npm run dev로 실행해 주세요.',
    );
  return send(404, 'Not found');
});
server.on('upgrade', (req, socket, head) => {
  if (
    !frontend ||
    !allowRequest(req) ||
    (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`)
  ) {
    socket.destroy();
    return;
  }
  frontend.upgrade(req, socket, head);
});
server.on('error', (error) => {
  console.error(
    error.code === 'EADDRINUSE'
      ? `Port ${port} is in use. Stop the existing server or run with --port ${port < 65535 ? port + 1 : 5173}.`
      : error.message,
  );
  clearInterval(autoBackupTimer);
  db.close();
  process.exitCode = 1;
});
server.listen(port, config.host, () => {
  console.log(`DB: ${dbPath}`);
  console.log(
    `SEA THE ANSWER (Next.js): http://127.0.0.1:${port}\nMode: ${config.lan ? 'LAN' : 'Local (this PC only)'}`,
  );
  if (config.lan) {
    for (const entry of interfaces)
      console.log(`LAN (${entry.name}): http://${entry.address}:${port}`);
    if (!interfaces.length)
      console.log(
        'No LAN IPv4 address found. Connect Wi-Fi/Ethernet, then restart.',
      );
    console.log(
      "Other devices: use a LAN URL above on the same network. Reports share this PC's database.",
    );
  }
  console.log('Press Ctrl+C to stop.');
});
server.requestTimeout = 35000;
server.headersTimeout = 10000;
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => {
    clearInterval(autoBackupTimer);
    server.close(() => {
      db.close();
      process.exit(0);
    });
  });
