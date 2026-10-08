// Internal API server. Browsers open the Next.js public port; Next.js rewrites
// `/api/*` to this server (frontend/next.config.mjs). See docs/adr/0006.
import http from 'node:http';
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
    [
      'Usage: node backend/server.mjs [--port 8000] [--public-port 5173] [--lan]',
      '--port: API port on 127.0.0.1 (default: port of HAEDAP_API_ORIGIN, else 8000). Next.js forwards /api/* here.',
      '--public-port: the Next.js port users open (PORT, default 5173).',
      '--lan: also accept this PC\'s LAN addresses as the host name (start Next.js with -H 0.0.0.0).',
    ].join('\n'),
  );
  process.exit(0);
}
const { port, publicPort } = config;
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
      `Open the address printed in the terminal (http://127.0.0.1:${publicPort}).`,
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
  return send(
    404,
    `API server only. Open http://127.0.0.1:${publicPort} (Next.js) for the screens.`,
  );
});
server.on('error', (error) => {
  console.error(
    error.code === 'EADDRINUSE'
      ? `API port ${port} is in use. Stop the existing server, or set HAEDAP_API_ORIGIN in .env (then rebuild for npm start).`
      : error.message,
  );
  clearInterval(autoBackupTimer);
  db.close();
  process.exitCode = 1;
});
server.listen(port, config.host, () => {
  console.log(`DB: ${dbPath}`);
  console.log(`API: http://127.0.0.1:${port} (internal, Next.js /api/* rewrite)`);
  console.log(
    `SEA THE ANSWER (Next.js): http://127.0.0.1:${publicPort}\nMode: ${config.lan ? 'LAN' : 'Local (this PC only)'}`,
  );
  if (config.lan) {
    for (const entry of interfaces)
      console.log(`LAN (${entry.name}): http://${entry.address}:${publicPort}`);
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
