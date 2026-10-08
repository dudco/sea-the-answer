import test from 'node:test';
import assert from 'node:assert/strict';
import { createNetworkPolicy, lanInterfaces, requestHost, serverOptions } from '../network.mjs';

const interfaces = [{ name: 'Wi-Fi', address: '192.168.10.5', cidr: '192.168.10.5/24' }];
const req = (host, remoteAddress = '127.0.0.1') => ({ headers: { host }, socket: { remoteAddress } });
const fwd = (host, forwarded, remoteAddress = '127.0.0.1') => ({ headers: { host, 'x-forwarded-host': forwarded }, socket: { remoteAddress } });

test('API CLI: internal port, public (Next.js) port, LAN flag; rejects invalid inputs', () => {
  assert.deepEqual(serverOptions([], {}), { lan: false, port: 8000, publicPort: 5173, host: '127.0.0.1', help: false });
  assert.deepEqual(serverOptions(['--lan', '--port', '8100', '--public-port', '5174'], { PORT: '5178' }), { lan: true, port: 8100, publicPort: 5174, host: '127.0.0.1', help: false });
  assert.equal(serverOptions([], { PORT: '5199' }).publicPort, 5199);
  assert.equal(serverOptions([], { HAEDAP_API_ORIGIN: 'http://127.0.0.1:8123' }).port, 8123);
  assert.equal(serverOptions(['--port', '8200'], { HAEDAP_API_ORIGIN: 'http://127.0.0.1:8123' }).port, 8200);
  assert.equal(serverOptions(['--help'], {}).help, true);
  for (const args of [['--port'], ['--port', '0'], ['--port', '65536'], ['--port', '2.5'], ['--port', '-1'], ['--port', '--lan'], ['--public-port'], ['--public-port', '0'], ['--unknown']]) assert.throws(() => serverOptions(args, {}), String(args));
  for (const origin of ['http://0.0.0.0:8000', 'http://127.0.0.1', 'http://evil.example:8000']) assert.throws(() => serverOptions([], { HAEDAP_API_ORIGIN: origin }), origin);
});
test('direct calls: loopback peer and the API port only', () => {
  const allow = createNetworkPolicy({ lan: false, port: 8000, publicPort: 5173 }, interfaces);
  assert.ok(allow(req('localhost:8000')));
  assert.ok(allow(req('127.0.0.1:8000', '::ffff:127.0.0.1')));
  assert.equal(allow(req('127.0.0.1:5173')), false);
  assert.equal(allow(req('127.0.0.1:8000', '192.168.10.20')), false);
  assert.equal(allow(req('evil.example:8000')), false);
});
test('via Next.js proxy: X-Forwarded-Host must be this PC on the public port; never trusted from non-loopback peers', () => {
  const local = createNetworkPolicy({ lan: false, port: 8000, publicPort: 5173 }, interfaces);
  assert.ok(local(fwd('127.0.0.1:8000', '127.0.0.1:5173')));
  assert.ok(local(fwd('127.0.0.1:8000', 'localhost:5173')));
  for (const host of ['127.0.0.1:8000', '127.0.0.1:5174', '192.168.10.5:5173', 'evil.example:5173', '127.0.0.1:5173, evil.example']) assert.equal(local(fwd('127.0.0.1:8000', host)), false, host);
  assert.equal(local(fwd('127.0.0.1:8000', '127.0.0.1:5173', '192.168.10.25')), false);
  assert.equal(requestHost(fwd('127.0.0.1:8000', 'evil.example:5173', '192.168.10.25')), '127.0.0.1:8000');
  assert.equal(requestHost(fwd('127.0.0.1:8000', '127.0.0.1:5173')), '127.0.0.1:5173');
  const lan = createNetworkPolicy({ lan: true, port: 8000, publicPort: 5173 }, interfaces);
  assert.ok(lan(fwd('127.0.0.1:8000', '192.168.10.5:5173')));
  for (const host of ['192.168.10.99:5173', '192.168.10.5:9999', '192.168.10.5:5173@evil.example', '0.0.0.0:5173']) assert.equal(lan(fwd('127.0.0.1:8000', host)), false, host);
});
test('LAN interface discovery excludes IPv6 and loopback; remote peers are never allowed', () => {
  assert.deepEqual(lanInterfaces({ loopback: [{ internal: true, family: 'IPv4', address: '127.0.0.1' }], wifi: [
    { internal: false, family: 'IPv6', address: '::1' }, { internal: false, family: 'IPv4', address: '10.0.0.5', cidr: '10.0.0.5/24' }] }),
  [{ name: 'wifi', address: '10.0.0.5', cidr: '10.0.0.5/24' }]);
  const allow = createNetworkPolicy({ lan: true, port: 8000, publicPort: 5173 }, [{ name: 'broken', address: '10.0.0.5', cidr: '10.0.0.5/0' }]);
  assert.equal(allow(fwd('127.0.0.1:8000', '10.0.0.5:5173', '8.8.8.8')), false);
});
