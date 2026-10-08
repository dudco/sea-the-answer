import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import { lanInterfaces } from '../../backend/network.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
test('Windows launchers: CMD local, PowerShell local, CMD LAN; same-origin API on LAN address', { skip: process.platform !== 'win32', timeout: 300000 }, async () => {
  // Keep diagnostics, like the Chrome smoke check, for Windows launcher troubleshooting.
  mkdirSync(join(root, '.verification'), { recursive: true });
  const temp = mkdtempSync(join(root, '.verification', 'launcher-'));
  const results = [];
  try {
    const configurations = [
      { name: 'double-click entry point', command: 'cmd.exe', args: ['/d', '/c', 'start.cmd'], lan: false },
      { name: 'terminal entry point', command: 'powershell.exe', args: ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/start.ps1'], lan: false },
      { name: 'LAN double-click entry point', command: 'cmd.exe', args: ['/d', '/c', 'start.cmd', '-Lan'], lan: true },
    ];
    for (const [index, config] of configurations.entries()) {
      const probe = createServer(); probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
      const port = probe.address().port; await new Promise(r => probe.close(r));
      const child = spawn(config.command, [...config.args, '-Port', String(port)], { cwd: root, windowsHide: true,
        env: { ...process.env, HAEDAP_NO_PAUSE: '1', HAEDAP_DB_PATH: join(temp, `db-${index}.sqlite`), OPENAI_API_KEY: '', OPENAI_MODEL: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
      let logs = ''; child.stdout.on('data', d => { logs += d; }); child.stderr.on('data', d => { logs += d; });
      try {
        const local = `http://127.0.0.1:${port}`;
        let health;
        // The first Windows start may build Next.js before the public server opens.
        for (let i = 0; i < 1800; i++) {
          try { health = await (await fetch(local + '/api/health', { signal: AbortSignal.timeout(1000) })).json(); break; } catch { await new Promise(r => setTimeout(r, 100)); }
          if (child.exitCode !== null) break;
        }
        assert.ok(health?.ok, `${config.name}: ${logs}`);
        assert.equal((await fetch(local + '/')).status, 200);
        assert.ok(logs.includes(config.lan ? 'Mode: LAN' : 'Mode: Local'), logs);
        const setup=await fetch(local+'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-Haedap-Token':health.csrfToken},body:JSON.stringify({username:'admin',name:'관리자',password:'1234'})});
        assert.equal(setup.status,200);const cookie=setup.headers.getSetCookie().find(c=>c.startsWith('haedap_session=')).split(';')[0];
        if (config.lan) {
          const address = lanInterfaces()[0]?.address;
          if (address) {
            const base = `http://${address}:${port}`;
            assert.ok(logs.includes(base), logs);
            const remoteHealth = await (await fetch(base + '/api/health')).json(); assert.ok(remoteHealth.ok);
            const ask = await fetch(base + '/api/ask', { method: 'POST', headers: { Cookie:cookie, Origin: base, 'Content-Type': 'application/json', 'X-Haedap-Token': remoteHealth.csrfToken }, body: JSON.stringify({ question: '연료 황 함유량' }) });
            assert.equal(ask.status, 200); assert.ok((await ask.json()).evidence.length > 0);
            const foreign = await fetch(base + '/api/ask', { method: 'POST', headers: { Origin: 'https://evil.example', 'Content-Type': 'application/json', 'X-Haedap-Token': remoteHealth.csrfToken }, body: '{}' });
            assert.equal(foreign.status, 403);
            assert.equal((await fetch(base + '/data/haedap.sqlite')).status, 404);
          }
        }
        results.push({ entry: config.name, passed: true, lanAddressTested: config.lan ? lanInterfaces()[0]?.address || null : null });
      } finally {
        writeFileSync(join(temp, `server-${index}.log`), logs);
        if (child.exitCode === null && child.signalCode === null) {
          const exited = once(child, 'exit');
          execFileSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
          await exited;
        }
      }
    }
  } finally {
    writeFileSync(join(temp, 'results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), results }, null, 2));
  }
});
