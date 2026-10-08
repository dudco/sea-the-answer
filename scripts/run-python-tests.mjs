import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const python = process.env.HAEDAP_PYTHON || resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
if (!existsSync(python)) {
  console.error('Python 가상 환경이 없습니다. README의 FastAPI 설치 명령을 먼저 실행해 주세요.');
  process.exit(1);
}
const result = spawnSync(python, ['-m', 'pytest', 'backend/tests/test_fastapi_api.py', '-q', '-p', 'no:cacheprovider'], {
  cwd: root, stdio: 'inherit', windowsHide: true,
});
process.exitCode = result.status === null ? 1 : result.status;
