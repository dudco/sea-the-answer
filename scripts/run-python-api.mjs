import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
process.chdir(root);
try { process.loadEnvFile(resolve(root, '.env')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
const python = process.env.HAEDAP_PYTHON || resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
if (!existsSync(python)) {
  console.error('Python 가상 환경이 없습니다. README의 FastAPI 설치 명령을 먼저 실행해 주세요.');
  process.exit(1);
}
const origin = new URL(process.env.HAEDAP_API_ORIGIN || 'http://127.0.0.1:8000');
if (origin.hostname !== '127.0.0.1' || !origin.port) throw Error('HAEDAP_API_ORIGIN must use 127.0.0.1:<port>');
const child = spawn(python, ['-m', 'uvicorn', 'backend.pyapi.workspace_api:app', '--host', '127.0.0.1', '--port', origin.port, ...process.argv.slice(2)], {
  cwd: root, env: process.env, stdio: 'inherit', windowsHide: true,
});
child.on('exit', code => { process.exitCode = code || 0; });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
