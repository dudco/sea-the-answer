import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const child = spawn(
  process.execPath,
  ['node_modules/next/dist/bin/next', 'build', 'frontend', '--webpack'],
  {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      NEXT_TELEMETRY_DISABLED: '1',
      HAEDAP_NEXT_DIST: '.next',
    },
  },
);
child.on('error', (e) => {
  console.error(e.message);
  process.exitCode = 1;
});
child.on('exit', (code) => (process.exitCode = code ?? 1));
