import { networkInterfaces } from 'node:os';
import { BlockList, isIPv4 } from 'node:net';

export function serverOptions(args = process.argv.slice(2), env = process.env) {
  let lan = false, port = env.PORT || '5173', help = false, frontend = env.HAEDAP_FRONTEND_ORIGIN || null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--lan') lan = true;
    else if (args[i] === '--port') {
      if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error('--port requires a port number.');
      port = args[++i];
    } else if (args[i] === '--frontend') {
      if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error('--frontend requires a Next.js origin such as http://127.0.0.1:3000.');
      frontend = args[++i];
    } else if (args[i] === '--help') help = true;
    else throw new Error(`Unknown option: ${args[i]}. Use --help.`);
  }
  if (!/^\d+$/.test(String(port)) || Number(port) < 1 || Number(port) > 65535) throw new Error('Port must be an integer from 1 to 65535.');
  return { lan, port: Number(port), host: lan ? '0.0.0.0' : '127.0.0.1', help, frontend };
}

export function lanInterfaces(interfaces = networkInterfaces()) {
  return Object.entries(interfaces).flatMap(([name, entries]) => (entries || [])
    .filter(e => (e.family === 'IPv4' || e.family === 4) && !e.internal && isIPv4(e.address))
    .map(e => ({ name, address: e.address, cidr: e.cidr })));
}

// Allow only this server's actual IP addresses and connected IPv4 subnets.
// A LAN launch does not allow arbitrary Host headers or cross-origin browser requests.
export function createNetworkPolicy({ lan, port }, interfaces = lanInterfaces()) {
  const hosts = new Set(['127.0.0.1', 'localhost']);
  const clients = new BlockList();
  clients.addSubnet('127.0.0.0', 8, 'ipv4');
  if (lan) for (const entry of interfaces) {
    hosts.add(entry.address);
    const prefix = Number(entry.cidr?.split('/')[1]);
    // Exclude default-route-sized or broken masks from the client allowlist.
    if (Number.isInteger(prefix) && prefix >= 1 && prefix <= 32) clients.addSubnet(entry.address, prefix, 'ipv4');
    else clients.addAddress(entry.address, 'ipv4');
  }
  return req => {
    const match = /^(localhost|\d{1,3}(?:\.\d{1,3}){3})(?::(\d+))?$/.exec(req.headers.host || '');
    if (!match || !hosts.has(match[1]) || Number(match[2] || 80) !== port) return false;
    const remote = (req.socket.remoteAddress || '').replace(/^::ffff:/, '');
    return isIPv4(remote) && clients.check(remote, 'ipv4');
  };
}
