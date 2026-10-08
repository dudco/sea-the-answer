// One public gateway, one loopback Next.js process. API/cookies stay same-origin.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { once } from 'node:events';
import { serverOptions } from '../backend/network.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));
process.chdir(root);
try {
  process.loadEnvFile(resolve(root, '.env'));
} catch (e) {
  if (e.code !== 'ENOENT') throw e;
}
const args = process.argv.slice(2),
  dev = args.includes('--dev'),
  serverArgs = args.filter((x) => x !== '--dev');
const config = serverOptions(serverArgs);
if (config.help) {
  console.log(
    'npm start -- [--lan] [--port 5173]\nnpm run dev -- [--lan] [--port 5173]',
  );
  process.exit(0);
}
if (!dev) {
  try {
    await access(resolve(root, 'frontend/.next/BUILD_ID'));
  } catch {
    console.error('먼저 npm run build를 실행해 주세요.');
    process.exit(1);
  }
}
const probe = createServer();
probe.listen(0, '127.0.0.1');
await once(probe, 'listening');
const nextPort = probe.address().port;
await new Promise((r) => probe.close(r));
const children = [],
  env = {
    ...process.env,
    NEXT_TELEMETRY_DISABLED: '1',
    HAEDAP_NEXT_DIST: dev ? '.next-dev' : '.next',
  };
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
    children.map((c) =>
      c.exitCode === null ? once(c, 'exit').catch(() => {}) : null,
    ),
  ).finally(() => process.exit(code));
}
function launch(file, argv, overrides = {}) {
  const child = spawn(process.execPath, [file, ...argv], {
    cwd: root,
    env: { ...env, ...overrides },
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
const next = launch(resolve(root, 'node_modules/next/dist/bin/next'), [
  dev ? 'dev' : 'start',
  'frontend',
  ...(dev ? ['--webpack'] : []),
  '-H',
  '127.0.0.1',
  '-p',
  String(nextPort),
]);
const origin = `http://127.0.0.1:${nextPort}`;
let ready = false;
for (let n = 0; n < 300 && !stopping; n++) {
  try {
    const response = await fetch(origin + '/chat', {
      signal: AbortSignal.timeout(1000),
    });
    await response.body?.cancel();
    if (response.status < 500) {
      ready = true;
      break;
    }
  } catch {}
  await new Promise((r) => setTimeout(r, 200));
}
if (!ready) {
  console.error('Next.js 시작 시간을 초과했습니다.');
  stop(1);
} else {
  launch(resolve(root, 'backend/server.mjs'), serverArgs, {
    HAEDAP_FRONTEND_ORIGIN: origin,
  });
}
