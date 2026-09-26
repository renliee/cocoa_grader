"""Exercise the real HTTP and SQLite foundation without a model or Docker."""
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ''

    def request(self, path, method='GET', body=None, csrf=True):
        headers = {'Origin': self.base}
        if method != 'GET' and csrf and self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, data=raw, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {'detail': raw.decode('utf-8', errors='replace')}

    def signup(self, name, login):
        status, data = self.request('/api/auth/signup', 'POST', {
            'display_name': name, 'login': login,
            'password': 'correct-horse-123', 'password_confirmation': 'correct-horse-123',
        })
        assert status == 200, data
        self.csrf = data['csrf_token']
        return data


class FoundationFlow(unittest.TestCase):
    def run_server(self):
        env = dict(os.environ, KAKAO_DATA_DIR=str(self.temp_path), PYTHONIOENCODING='utf-8')
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'backend/serve_local.py'),
                                      '--without-cv', '--port', str(self.port)],
                                     cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.base + '/api/health', timeout=.5) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                pass
            if self.proc.poll() is not None:
                self.fail('Backend exited during startup')
            time.sleep(.1)
        self.fail('Backend did not become ready')

    def stop_server(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)

    def test_signup_supplier_lot_draft_restart_and_owner_isolation(self):
        data_parent = ROOT / 'data'
        data_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=data_parent) as temp:
            self.temp_path = Path(temp).resolve()
            self.assertTrue(self.temp_path.is_relative_to(ROOT.resolve()))
            self.port = free_port()
            self.base = f'http://127.0.0.1:{self.port}'
            self.run_server()
            try:
                preview_port = free_port()
                preview_base = f'http://127.0.0.1:{preview_port}'
                preview = subprocess.Popen([sys.executable, str(ROOT / 'frontend/serve.py'),
                                            '--port', str(preview_port), '--backend-port', str(self.port)],
                                           cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        try:
                            with urllib.request.urlopen(preview_base + '/', timeout=.5) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            time.sleep(.1)
                    else:
                        self.fail('Frontend proxy did not become ready')
                    through_ui = Client(preview_base)
                    through_ui.signup('Proxy QC', 'proxy')
                    status, via_proxy = through_ui.request('/api/suppliers', 'POST',
                                                           {'name': 'Pemasok proxy', 'code': 'PROX'})
                    self.assertEqual(status, 201)
                    self.assertEqual(through_ui.request('/api/lots', 'POST',
                                                        {'supplier_id': via_proxy['id']})[0], 201)
                    self.assertEqual(through_ui.request('/api/dashboard')[1]['attention']['drafts'], 1)
                    for route in ('/settings/guide', '/lots/' + 'a' * 32, '/analysis/' + 'b' * 32 + '/lot',
                                  '/report/' + 'c' * 43):
                        with urllib.request.urlopen(preview_base + route) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn(b'id="main"', response.read())
                    # PUT reaches FastAPI instead of the preview server's unsupported-method page.
                    self.assertEqual(through_ui.request('/api/drafts/' + 'a' * 32 + '/photos/' + 'b' * 32,
                                                        'PUT', {})[0], 422)
                finally:
                    preview.terminate()
                    preview.wait(timeout=10)
                alice = Client(self.base)
                bob = Client(self.base)
                self.assertEqual(alice.request('/api/dashboard')[0], 401)
                alice.signup('Alice QC', 'Alice')
                bob.signup('Bob QC', 'Bob')
                status, profile = alice.request('/api/account/profile', 'PATCH', {'display_name': 'Alice Cocoa QC'})
                self.assertEqual(status, 200)
                self.assertEqual(profile['display_name'], 'Alice Cocoa QC')
                self.assertEqual(alice.request('/api/auth/me')[1]['user']['display_name'], 'Alice Cocoa QC')
                self.assertEqual(bob.request('/api/account/profile', 'PATCH', {'display_name': 'Other User'})[1]['display_name'], 'Other User')
                self.assertEqual(alice.request('/api/auth/me')[1]['user']['display_name'], 'Alice Cocoa QC')
                self.assertEqual(alice.request('/api/account/profile', 'PATCH', {'display_name': '  '})[0], 400)
                self.assertEqual(alice.request('/api/account/profile', 'PATCH', {'display_name': 'Changed'}, csrf=False)[0], 403)
                status, supplier = alice.request('/api/suppliers', 'POST', {'name': 'Pak Ahmad', 'code': 'AHMD'})
                self.assertEqual(status, 201)
                status, performance = alice.request(f"/api/suppliers/{supplier['id']}/performance")
                self.assertEqual(status, 200)
                self.assertEqual(performance['total_lots'], 0)
                self.assertIsNone(performance['mean_fermented'])
                self.assertEqual(bob.request(f"/api/suppliers/{supplier['id']}/performance")[0], 404)
                self.assertEqual(bob.request('/api/suppliers')[1]['items'], [])
                self.assertEqual(alice.request(f"/api/suppliers/{supplier['id']}", 'PATCH', {
                    'name': 'Koperasi Ahmad', 'contact': '08120000', 'notes': 'kontak aktif',
                })[0], 200)
                status, first = alice.request('/api/lots', 'POST', {'supplier_id': supplier['id']})
                self.assertEqual(status, 201)
                status, second = alice.request('/api/lots', 'POST', {'supplier_id': supplier['id']})
                self.assertEqual(status, 201)
                self.assertTrue(first['human_id'].startswith('AHMD-'))
                self.assertEqual(alice.request(f"/api/suppliers/{supplier['id']}", 'DELETE')[0], 409)
                self.assertEqual(alice.request(f"/api/suppliers/{supplier['id']}/archive", 'POST')[0], 200)
                self.assertEqual(alice.request('/api/suppliers')[1]['items'], [])
                archived = alice.request('/api/suppliers?include_archived=true')[1]['items']
                self.assertEqual(archived[0]['lot_count'], 2)
                self.assertEqual(alice.request(f"/api/suppliers/{supplier['id']}/restore", 'POST')[0], 200)
                self.assertEqual(alice.request('/api/suppliers')[1]['items'][0]['name'], 'Koperasi Ahmad')
                self.assertEqual(int(second['human_id'].rsplit('-', 1)[1]), int(first['human_id'].rsplit('-', 1)[1]) + 1)
                self.assertEqual(bob.request(f"/api/drafts/{first['id']}")[0], 404)
                self.assertEqual(bob.request('/api/lots', 'POST', {'supplier_id': supplier['id']})[0], 404)
                self.assertEqual(alice.request('/api/dashboard')[1]['lot_count'], 0)
                self.assertEqual(alice.request('/api/dashboard')[1]['attention']['drafts'], 2)
                self.assertEqual(len(alice.request('/api/drafts')[1]['items']), 2)
                self.assertEqual(alice.request(f"/api/drafts/{first['id']}", 'PATCH', {
                    'expected_version': 1, 'weight_kg': '52.5', 'notes': 'Incoming sample', 'wizard_step': 'lot',
                })[0], 200)
                self.assertEqual(alice.request(f"/api/drafts/{first['id']}", 'PATCH', {
                    'expected_version': 1, 'weight_kg': '99', 'notes': 'stale', 'wizard_step': 'lot',
                })[0], 409)
                self.assertEqual(alice.request(f"/api/drafts/{first['id']}", 'PATCH', {
                    'expected_version': 2, 'weight_kg': '-4', 'notes': '', 'wizard_step': 'lot',
                })[0], 400)
                self.assertEqual(alice.request(f"/api/drafts/{first['id']}", 'PATCH', {
                    'expected_version': 2, 'weight_kg': '53', 'notes': '', 'wizard_step': 'lot',
                }, csrf=False)[0], 403)
                self.assertEqual(bob.request('/api/dashboard')[1]['attention']['drafts'], 0)
                self.assertEqual(alice.request('/api/lots', 'POST', {})[0], 422)
                self.assertEqual(alice.request('/api/lots', 'POST', {'supplier_id': None})[0], 422)
                self.assertEqual(alice.request('/api/lots', 'POST', {'supplier_id': ''})[0], 422)
                self.assertEqual(alice.request('/api/suppliers/' + supplier['id'] + '/archive', 'POST')[0], 200)
                self.assertEqual(alice.request('/api/lots', 'POST', {'supplier_id': supplier['id']})[0], 404)
                # An existing draft can still use its archived supplier.
                self.assertEqual(alice.request(f"/api/drafts/{second['id']}", 'PATCH', {
                    'expected_version': 1, 'supplier_id': supplier['id'], 'wizard_step': 'sample',
                })[0], 200)
                self.assertEqual(alice.request('/api/suppliers/' + supplier['id'] + '/restore', 'POST')[0], 200)
                status, quick = alice.request('/api/lots', 'POST', {'supplier_id': supplier['id']})
                self.assertEqual(status, 201)
                self.assertTrue(quick['human_id'].startswith('AHMD-'))
                status, assigned = alice.request(f"/api/drafts/{quick['id']}", 'PATCH', {
                    'expected_version': 1, 'supplier_id': supplier['id'],
                    'notes': '', 'wizard_step': 'sample',
                })
                self.assertEqual(status, 200)
                self.assertTrue(assigned['human_id'].startswith('AHMD-'))
                status, unassigned = alice.request(f"/api/drafts/{quick['id']}", 'PATCH', {
                    'expected_version': 2, 'supplier_id': None,
                    'notes': '', 'wizard_step': 'sample',
                })
                self.assertEqual(status, 400)
                self.assertEqual(alice.request(f"/api/drafts/{quick['id']}")[1]['supplier_id'], supplier['id'])
                self.assertEqual(alice.request(f"/api/drafts/{quick['id']}", 'DELETE')[0], 200)
                self.assertEqual(alice.request(f"/api/drafts/{quick['id']}")[0], 404)
                status, unused = alice.request('/api/suppliers', 'POST', {'name': 'Tidak Terpakai', 'code': 'NPAK'})
                self.assertEqual(status, 201)
                self.assertEqual(alice.request(f"/api/suppliers/{unused['id']}", 'DELETE')[0], 200)
                self.assertEqual(len(alice.request('/api/suppliers')[1]['items']), 1)
            finally:
                self.stop_server()
            self.run_server()
            try:
                status, resumed = alice.request(f"/api/drafts/{first['id']}")
                self.assertEqual(status, 200)
                self.assertEqual(resumed['weight_kg'], '52.5')
                self.assertEqual(resumed['notes'], 'Incoming sample')
                self.assertEqual(alice.request('/api/auth/me')[0], 200)
                self.assertEqual(alice.request('/api/auth/me')[1]['user']['display_name'], 'Alice Cocoa QC')
                self.assertEqual(alice.request('/api/dashboard')[1]['mean_fermented'], None)
            finally:
                self.stop_server()


if __name__ == '__main__':
    unittest.main()
