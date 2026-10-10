import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
try { process.loadEnvFile(resolve(root, '.env')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
const uv = process.env.HAEDAP_UV || 'uv';
const result = spawnSync(uv, ['run', '--locked', '--project', 'backend', 'python', '-m', 'pytest', 'backend/tests/test_fastapi_api.py', '-q', '-p', 'no:cacheprovider'], {
  cwd: root, stdio: 'inherit', windowsHide: true,
});
process.exitCode = result.status === null ? 1 : result.status;
