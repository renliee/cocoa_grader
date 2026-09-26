"""HTTP precheck, saved inputs, review, restart, and draft deletion."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from uuid import uuid4

from test_foundation import Client, ROOT, free_port


def upload(client, draft_id, image_path, key, photo_id=None):
    raw = image_path.read_bytes()
    boundary = 'kakao-' + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{image_path.name}"\r\nContent-Type: image/jpeg\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
    path = f'/api/drafts/{draft_id}/photos' + (f'/{photo_id}' if photo_id else '')
    request = urllib.request.Request(client.base + path, data=body,
                                     method='PUT' if photo_id else 'POST', headers={
                                         'Origin': client.base,
                                         'X-CSRF-Token': client.csrf,
                                         'Idempotency-Key': key,
                                         'Content-Type': f'multipart/form-data; boundary={boundary}',
                                     })
    with client.opener.open(request, timeout=30) as response:
        return response.status, json.load(response)


class PrecheckFlow(unittest.TestCase):
    def test_precheck_is_persisted_and_deleted_with_draft(self):
        parent = ROOT / 'data'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            data_dir = Path(temp).resolve()
            self.assertTrue(data_dir.is_relative_to(ROOT.resolve()))
            port = free_port()
            base = f'http://127.0.0.1:{port}'
            env = dict(os.environ, KAKAO_DATA_DIR=str(data_dir), PYTHONIOENCODING='utf-8')

            def start():
                process = subprocess.Popen([sys.executable, str(ROOT / 'backend/serve_local.py'),
                                            '--without-cv', '--port', str(port)], cwd=str(ROOT), env=env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(base + '/api/health', timeout=.5):
                            return process
                    except OSError:
                        if process.poll() is not None:
                            self.fail('Backend exited during startup')
                        time.sleep(.1)
                self.fail('Backend did not become ready')

            process = start()
            try:
                alice, bob = Client(base), Client(base)
                alice.signup('Analyst', 'analyst')
                bob.signup('Other', 'other')
                _, supplier = alice.request('/api/suppliers', 'POST', {'name': 'Pemasok Uji', 'code': 'UJI'})
                status, draft = alice.request('/api/lots', 'POST', {'supplier_id': supplier['id']})
                self.assertEqual(status, 201)
                self.assertTrue(draft['human_id'].startswith('UJI-'))
                bad_image = data_dir / 'bad.jpg'
                bad_image.write_bytes(b'not an image')
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    upload(alice, draft['id'], bad_image, uuid4().hex)
                self.assertEqual(invalid.exception.code, 400)
                image = ROOT / 'backend/tests/images/tray_real_01.jpg'
                upload_key = uuid4().hex
                status, photo = upload(alice, draft['id'], image, upload_key)
                self.assertEqual(status, 201)
                self.assertEqual(upload(alice, draft['id'], image, upload_key)[1]['id'], photo['id'])
                with self.assertRaises(urllib.error.HTTPError) as duplicate:
                    upload(alice, draft['id'], ROOT / 'backend/tests/images/tray_real_02.jpg', upload_key)
                self.assertEqual(duplicate.exception.code, 409)
                self.assertEqual(bob.request(f"/api/drafts/{draft['id']}/photos")[0], 404)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    status, listing = alice.request(f"/api/drafts/{draft['id']}/photos")
                    self.assertEqual(status, 200)
                    photo = listing['items'][0]
                    if photo['status'] in ('ready', 'warning', 'invalid', 'failed'):
                        break
                    time.sleep(.25)
                self.assertIn(photo['status'], ('ready', 'warning'), photo)
                self.assertEqual(photo['usable_count'], 16)
                self.assertEqual(photo['detected_count'], photo['usable_count'] + photo['excluded_count'])
                self.assertEqual(sum(photo['excluded_reasons'].values()), photo['excluded_count'])
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}")[1]['input_version'], 1)
                self.assertEqual(photo['review_state'], 'included')
                manifest_path = data_dir / 'assets' / alice.request('/api/auth/me')[1]['user']['id'] / photo['id'] / 'precheck.json'
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                self.assertEqual(len([obj for obj in manifest['objects'] if obj['disposition'] == 'usable']), 16)
                for obj in manifest['objects']:
                    if obj['disposition'] == 'usable':
                        self.assertTrue((data_dir / obj['prepared_key']).exists())
                manifest_sha = manifest_path.read_bytes()
            finally:
                process.terminate()
                process.wait(timeout=10)
            process = start()
            try:
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}/photos")[1]['items'][0]['usable_count'], 16)
                self.assertEqual(manifest_path.read_bytes(), manifest_sha)
                status, replacement = upload(alice, draft['id'],
                                              ROOT / 'backend/tests/images/tray_real_02.jpg',
                                              uuid4().hex, photo['id'])
                self.assertEqual(status, 200)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    listing = alice.request(f"/api/drafts/{draft['id']}/photos")[1]
                    replacement = listing['items'][0]
                    if replacement['status'] in ('ready', 'warning', 'invalid', 'failed'):
                        break
                    time.sleep(.25)
                self.assertEqual(len(listing['items']), 1)
                self.assertEqual(replacement['usable_count'], 20)
                self.assertFalse(manifest_path.parent.exists())
                replacement_dir = data_dir / 'assets' / alice.request('/api/auth/me')[1]['user']['id'] / replacement['id']
                self.assertTrue(replacement_dir.exists())
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}/photos/{replacement['id']}", 'DELETE')[0], 200)
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}/photos")[1]['items'], [])
                self.assertFalse(replacement_dir.exists())
                # Clear-all checks ownership and sample version, retaining the same lot.
                _, added = upload(alice, draft['id'], image, uuid4().hex)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    listing = alice.request(f"/api/drafts/{draft['id']}/photos")[1]
                    if not listing['summary']['processing_count']:
                        break
                    time.sleep(.25)
                current = alice.request(f"/api/drafts/{draft['id']}")[1]
                clear_path = f"/api/drafts/{draft['id']}/photos"
                body = {'expected_input_version': current['input_version']}
                self.assertEqual(bob.request(clear_path, 'DELETE', body)[0], 404)
                self.assertEqual(alice.request(clear_path, 'DELETE', {
                    'expected_input_version': current['input_version'] - 1})[0], 409)
                self.assertEqual(len(alice.request(clear_path)[1]['items']), 1)
                status, cleared = alice.request(clear_path, 'DELETE', body)
                self.assertEqual(status, 200)
                self.assertEqual(cleared['deleted_count'], 1)
                self.assertEqual(alice.request(clear_path)[1]['items'], [])
                after = alice.request(f"/api/drafts/{draft['id']}")[1]
                self.assertEqual(after['lot_id'], current['lot_id'])
                self.assertEqual(after['supplier_id'], supplier['id'])
                self.assertEqual(after['input_version'], current['input_version'] + 1)
                self.assertIsNone(after['selected_run_id'])
                self.assertFalse((replacement_dir.parent / added['id']).exists())
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}", 'DELETE')[0], 200)
                self.assertEqual(alice.request(f"/api/drafts/{draft['id']}")[0], 404)
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
