import http from 'node:http';
import net from 'node:net';
// Only an explicitly configured loopback Next.js process is a valid upstream.
export function frontendProxy(origin) {
  if (!origin) return null;
  const url = new URL(origin);
  if (
    url.protocol !== 'http:' ||
    url.hostname !== '127.0.0.1' ||
    url.username ||
    url.password ||
    url.pathname !== '/'
  )
    throw Error('HAEDAP_FRONTEND_ORIGIN must be http://127.0.0.1:<port>');
  const target = { hostname: '127.0.0.1', port: Number(url.port) };
  return {
    request(req, res) {
      const upstream = http.request(
        {
          ...target,
          path: req.url,
          method: req.method,
          headers: {
            ...req.headers,
            'x-forwarded-host': req.headers.host,
            'x-forwarded-proto': 'http',
          },
        },
        (reply) => {
          res.writeHead(reply.statusCode, reply.headers);
          reply.pipe(res);
        },
      );
      upstream.on('error', () => {
        if (!res.headersSent)
          res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(
          'Next.js 화면 서버에 연결할 수 없습니다. 시작 명령을 다시 실행해 주세요.',
        );
      });
      req.on('aborted', () => upstream.destroy());
      req.pipe(upstream);
    },
    upgrade(req, socket, head) {
      const upstream = net.connect(target.port, target.hostname, () => {
        const headers = Object.entries(req.headers).flatMap(([k, v]) =>
          Array.isArray(v) ? v.map((x) => `${k}: ${x}`) : [`${k}: ${v}`],
        );
        upstream.write(
          `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n${headers.join('\r\n')}\r\n\r\n`,
        );
        if (head.length) upstream.write(head);
        socket.pipe(upstream).pipe(socket);
      });
      upstream.on('error', () => socket.destroy());
      socket.on('error', () => upstream.destroy());
      socket.on('close', () => upstream.destroy());
    },
  };
}
