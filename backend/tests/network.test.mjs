import test from 'node:test';
import assert from 'node:assert/strict';
import { createNetworkPolicy, lanInterfaces, serverOptions } from '../network.mjs';

const interfaces = [{ name: 'Wi-Fi', address: '192.168.10.5', cidr: '192.168.10.5/24' }];
const req = (host, remoteAddress = '127.0.0.1') => ({ headers: { host }, socket: { remoteAddress } });

test('server CLI defaults local, supports LAN and port overrides, rejects invalid inputs', () => {
  assert.deepEqual(serverOptions([], {}), { lan: false, port: 5173, host: '127.0.0.1', help: false });
  assert.deepEqual(serverOptions(['--lan', '--port', '5174'], { PORT: '5178' }), { lan: true, port: 5174, host: '0.0.0.0', help: false });
  assert.equal(serverOptions([], { PORT: '5199' }).port, 5199);
  assert.equal(serverOptions(['--help'], {}).help, true);
  for (const args of [['--port'], ['--port', '0'], ['--port', '65536'], ['--port', '2.5'], ['--port', '-1'], ['--port', '--lan'], ['--unknown']]) assert.throws(() => serverOptions(args, {}));
});
test('local mode denies LAN Host headers and non-local clients', () => {
  const allow = createNetworkPolicy({ lan: false, port: 5173 }, interfaces);
  assert.ok(allow(req('localhost:5173')));
  assert.ok(allow(req('127.0.0.1:5173', '::ffff:127.0.0.1')));
  assert.equal(allow(req('192.168.10.5:5173')), false);
  assert.equal(allow(req('127.0.0.1:5173', '192.168.10.20')), false);
  assert.equal(allow(req('127.0.0.1:5174')), false);
});
test('LAN mode allows this server address and connected subnet, not arbitrary hosts or clients', () => {
  const allow = createNetworkPolicy({ lan: true, port: 5173 }, interfaces);
  assert.ok(allow(req('192.168.10.5:5173', '192.168.10.25')));
  assert.ok(allow(req('192.168.10.5:5173', '::ffff:192.168.10.25')));
  for (const host of ['evil.example:5173', '192.168.10.99:5173', '192.168.10.5:9999', '192.168.10.5:5173@evil.example', '0.0.0.0:5173']) assert.equal(allow(req(host, '192.168.10.25')), false, host);
  assert.equal(allow(req('192.168.10.5:5173', '198.51.100.5')), false);
});
test('LAN interface discovery excludes IPv6 and loopback; invalid masks never allow all clients', () => {
  assert.deepEqual(lanInterfaces({ loopback: [{ internal: true, family: 'IPv4', address: '127.0.0.1' }], wifi: [
    { internal: false, family: 'IPv6', address: '::1' }, { internal: false, family: 'IPv4', address: '10.0.0.5', cidr: '10.0.0.5/24' }] }),
  [{ name: 'wifi', address: '10.0.0.5', cidr: '10.0.0.5/24' }]);
  const allow = createNetworkPolicy({ lan: true, port: 5173 }, [{ name: 'broken', address: '10.0.0.5', cidr: '10.0.0.5/0' }]);
  assert.equal(allow(req('10.0.0.5:5173', '8.8.8.8')), false);
});
