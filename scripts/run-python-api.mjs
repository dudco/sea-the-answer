import { spawn } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
process.chdir(root);
try { process.loadEnvFile(resolve(root, '.env')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
const uv = process.env.HAEDAP_UV || 'uv';
const origin = new URL(process.env.HAEDAP_API_ORIGIN || 'http://127.0.0.1:8000');
if (origin.hostname !== '127.0.0.1' || !origin.port) throw Error('HAEDAP_API_ORIGIN must use 127.0.0.1:<port>');
const child = spawn(uv, ['run', '--locked', '--project', 'backend', 'uvicorn', 'backend.pyapi.workspace_api:app', '--host', '127.0.0.1', '--port', origin.port, ...process.argv.slice(2)], {
  cwd: root, env: process.env, stdio: 'inherit', windowsHide: true,
});
child.on('exit', code => { process.exitCode = code || 0; });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
