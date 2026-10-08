import { networkInterfaces } from 'node:os';
import { isIPv4 } from 'node:net';

// The API server is internal: it always listens on 127.0.0.1 and is reached
// through the Next.js proxy (`/api/*`, frontend/src/proxy.js). Users open the Next.js public port.
export function serverOptions(args = process.argv.slice(2), env = process.env) {
  // API port defaults to the port of HAEDAP_API_ORIGIN (the Next.js proxy target), else 8000.
  let apiPort = '8000';
  if (env.HAEDAP_API_ORIGIN) {
    const origin = new URL(env.HAEDAP_API_ORIGIN);
    if (origin.hostname !== '127.0.0.1' || !origin.port) throw new Error('HAEDAP_API_ORIGIN must be http://127.0.0.1:<port>.');
    apiPort = origin.port;
  }
  let lan = false, port = apiPort, publicPort = env.PORT || '5173', help = false;
  const value = (name, i) => {
    if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`${name} requires a port number.`);
    return args[i + 1];
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--lan') lan = true;
    else if (args[i] === '--port') port = value('--port', i++);
    else if (args[i] === '--public-port') publicPort = value('--public-port', i++);
    else if (args[i] === '--help') help = true;
    else throw new Error(`Unknown option: ${args[i]}. Use --help.`);
  }
  for (const p of [port, publicPort])
    if (!/^\d+$/.test(String(p)) || Number(p) < 1 || Number(p) > 65535) throw new Error('Port must be an integer from 1 to 65535.');
  return { lan, port: Number(port), publicPort: Number(publicPort), host: '127.0.0.1', help };
}

export function lanInterfaces(interfaces = networkInterfaces()) {
  return Object.entries(interfaces).flatMap(([name, entries]) => (entries || [])
    .filter(e => (e.family === 'IPv4' || e.family === 4) && !e.internal && isIPv4(e.address))
    .map(e => ({ name, address: e.address, cidr: e.cidr })));
}

const remoteOf = req => (req.socket?.remoteAddress || '').replace(/^::ffff:/, '');
const isLoopback = address => isIPv4(address) && address.startsWith('127.');

// Host the browser actually used. Next.js overwrites X-Forwarded-Host with the
// real Host header when proxying, so it is trusted only from a loopback peer.
// (X-Forwarded-For is passed through from the client by Next.js and is NOT trusted.)
export function requestHost(req) {
  const forwarded = req.headers['x-forwarded-host'];
  return forwarded && isLoopback(remoteOf(req)) ? String(forwarded) : req.headers.host || '';
}

// Allow only loopback peers (Next.js on this PC, tests, local tools) and only the
// host names of this machine: the public Next.js port when proxied, the API port
// when called directly. LAN mode adds this PC's LAN IPv4 addresses as host names.
export function createNetworkPolicy({ lan, port, publicPort = port }, interfaces = lanInterfaces()) {
  const hosts = new Set(['127.0.0.1', 'localhost']);
  if (lan) for (const entry of interfaces) hosts.add(entry.address);
  return req => {
    if (!isLoopback(remoteOf(req))) return false;
    const forwarded = !!req.headers['x-forwarded-host'];
    const match = /^(localhost|\d{1,3}(?:\.\d{1,3}){3})(?::(\d+))?$/.exec(requestHost(req));
    if (!match || !hosts.has(match[1])) return false;
    return Number(match[2] || 80) === (forwarded ? publicPort : port);
  };
}
