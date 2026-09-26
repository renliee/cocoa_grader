"""Serve the frontend and proxy API requests to a local backend without Docker."""
import argparse
from functools import partial
from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class PreviewHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        if urlsplit(self.path).path.startswith(('/report/', '/api/reports/')):
            return
        super().log_message(format, *args)

    def _proxy_api(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        forward = {key: value for key, value in self.headers.items()
                   if key.lower() not in ('connection', 'transfer-encoding', 'content-length')}
        forward['Host'] = self.headers.get('Host', '127.0.0.1:8080')
        connection = HTTPConnection('127.0.0.1', self.server.backend_port, timeout=300)
        try:
            connection.request(self.command, self.path, body=body, headers=forward)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in ('connection', 'transfer-encoding', 'content-length', 'server', 'date'):
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            payload = b'{"detail":"The analysis server is unavailable."}'
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        finally:
            connection.close()

    def do_GET(self):
        path = urlsplit(self.path).path.rstrip('/') or '/'
        if path.startswith('/api/'):
            self._proxy_api()
            return
        if path in ('/', '/history', '/suppliers', '/settings', '/login', '/signup', '/analysis/new') or path.startswith(('/analysis/', '/lots/', '/suppliers/', '/settings/', '/report/')):
            self.path = '/index.html'
        super().do_GET()

    do_POST = _proxy_api
    do_PATCH = _proxy_api
    do_PUT = _proxy_api
    do_DELETE = _proxy_api


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--backend-port', type=int, default=8000)
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=str(Path(__file__).resolve().parent))
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    server.backend_port = args.backend_port
    print(f'KakaoLens UI preview: http://{args.bind}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
