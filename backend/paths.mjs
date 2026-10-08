import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const projectRoot = fileURLToPath(new URL('../', import.meta.url));

// Keep explicit .env paths relative to the project root, including old versions.
// Never silently create an empty workspace when the previous default DB exists.
export function databasePath({
  root = projectRoot,
  configured = process.env.HAEDAP_DB_PATH,
} = {}) {
  if (configured) return resolve(root, configured);
  const current = resolve(root, 'backend/data/haedap.sqlite');
  const previous = resolve(root, 'data/haedap.sqlite');
  if (existsSync(current) && existsSync(previous)) {
    throw new Error(
      'DB가 backend/data와 data 양쪽에 있습니다. .env의 HAEDAP_DB_PATH에 사용할 DB 경로를 지정해 주세요.',
    );
  }
  return existsSync(previous) ? previous : current;
}
