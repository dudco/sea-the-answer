// `npm start`: production-style local run (built screens). Starts the internal
// API server, then `next start` on the public port. Development instead runs
// `npm run dev:backend` and `npm run dev:frontend` directly (docs/adr/0005, 0006).
import { spawn } from 'node:child_process';
import { access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { once } from 'node:events';
const root = fileURLToPath(new URL('../', import.meta.url));
process.chdir(root);
try {
  process.loadEnvFile(resolve(root, '.env'));
} catch (e) {
  if (e.code !== 'ENOENT') throw e;
}
const args = process.argv.slice(2);
let port = process.env.PORT || '5173',
  lan = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--lan') lan = true;
  else if (args[i] === '--port' && args[i + 1] && !args[i + 1].startsWith('--')) port = args[++i];
  else if (args[i] === '--help') {
    console.log('npm start -- [--lan] [--port 5173]');
    process.exit(0);
  } else if (args[i] === '--dev') {
    console.error('개발 모드는 npm run dev:backend 와 npm run dev:frontend 를 각각 실행합니다.');
    process.exit(1);
  } else {
    console.error(`Unknown option: ${args[i]}. Use --help.`);
    process.exit(1);
  }
}
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
  console.error('Port must be an integer from 1 to 65535.');
  process.exit(1);
}
// Must match the API origin the screens were built with (frontend/next.config.mjs).
const apiOrigin = new URL(process.env.HAEDAP_API_ORIGIN || 'http://127.0.0.1:8000');
if (apiOrigin.hostname !== '127.0.0.1' || !apiOrigin.port) {
  console.error('npm start requires HAEDAP_API_ORIGIN=http://127.0.0.1:<port>.');
  process.exit(1);
}
try {
  await access(resolve(root, 'frontend/.next/BUILD_ID'));
} catch {
  console.error('먼저 npm run build를 실행해 주세요.');
  process.exit(1);
}
const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const c of children) if (c.exitCode === null) c.kill('SIGTERM');
  const timer = setTimeout(() => {
    for (const c of children) if (c.exitCode === null) c.kill('SIGKILL');
    process.exit(code);
  }, 2500);
  timer.unref();
  Promise.all(
    children.map((c) => (c.exitCode === null ? once(c, 'exit').catch(() => {}) : null)),
  ).finally(() => process.exit(code));
}
function launch(file, argv) {
  const child = spawn(process.execPath, [file, ...argv], {
    cwd: root,
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1', HAEDAP_NEXT_DIST: '.next' },
    stdio: 'inherit',
    windowsHide: true,
  });
  children.push(child);
  child.on('error', (e) => {
    console.error(e.message);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping) stop(code || 1);
  });
  return child;
}
for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => stop(0));
launch(resolve(root, 'backend/server.mjs'), [
  '--port', apiOrigin.port, '--public-port', port, ...(lan ? ['--lan'] : []),
]);
launch(resolve(root, 'node_modules/next/dist/bin/next'), [
  'start', 'frontend', '-H', lan ? '0.0.0.0' : '127.0.0.1', '-p', port,
]);
