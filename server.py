"""Loopback-only demo server. Python 3.10+, no third-party dependencies."""
import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from lifecycle import ACTORS, PolicyError, Store

ROOT = Path(__file__).parent


def make_handler(store):
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json', extra=None):
            if content_type == 'application/json':
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            # Block DNS rebinding and cross-origin requests against localhost.
            host = self.headers.get('Host', '')
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            if host not in allowed or (origin and origin not in {'http://' + h for h in allowed}):
                self.send(403, {'error': 'Use the local demo origin.'})
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            path = urlparse(self.path).path
            try:
                with lock:
                    if path == '/api/state':
                        self.send(200, {'skills': store.list(), 'events': store.audit(), 'actors': ACTORS})
                    elif path.startswith('/api/download/'):
                        role = self.headers.get('X-Demo-Role', 'employee')
                        if role not in ACTORS:
                            raise PolicyError('Unknown demo role.')
                        artifact, name = store.download(int(path.split('/')[-1]), role)
                        self.send(200, artifact, 'application/zip', {'Content-Disposition': f'attachment; filename="{name}"'})
                    elif path in ['/', '/app.js', '/style.css']:
                        name = 'index.html' if path == '/' else path[1:]
                        content_type = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[name]
                        self.send(200, (ROOT / 'web' / name).read_bytes(), content_type)
                    else:
                        self.send(404, {'error': 'Not found'})
            except (PolicyError, ValueError) as exc:
                self.send(400, {'error': str(exc)})

        def do_POST(self):
            if not self.trusted():
                return
            try:
                role = self.headers.get('X-Demo-Role', 'employee')
                if role not in ACTORS:
                    raise PolicyError('Unknown demo role.')
                if self.headers.get('Content-Type') != 'application/json':
                    raise PolicyError('Send application/json.')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 20000:
                    raise PolicyError('Request must be 1–20000 bytes.')
                data = json.loads(self.rfile.read(length))
                with lock:
                    path = urlparse(self.path).path
                    if path == '/api/skills':
                        result = {'id': store.create(data, role)}
                    elif path == '/api/action' and isinstance(data, dict):
                        result = store.action(int(data.get('id', 0)), data.get('action', ''), role)
                    else:
                        self.send(404, {'error': 'Not found'})
                        return
                self.send(200, result)
            except (PolicyError, ValueError, TypeError) as exc:
                self.send(400, {'error': str(exc)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default=str(ROOT / '.data' / 'demo.sqlite3'))
    args = parser.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    store = Store(args.db)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store))
    print(f'Skill Demo: http://127.0.0.1:{args.port} — demo identities only', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        store.db.close()

if __name__ == '__main__':
    main()
