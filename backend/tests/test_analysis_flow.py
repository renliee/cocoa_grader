"""Run the saved-precheck to persisted-classification path with the real model."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from uuid import uuid4

from test_foundation import Client, ROOT, free_port
from test_precheck import upload


class AnalysisFlow(unittest.TestCase):
    def test_classifies_exact_saved_precheck_set_and_persists_result(self):
        parent = ROOT / 'data'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            data_dir = Path(temp).resolve()
            port = free_port()
            base = f'http://127.0.0.1:{port}'
            env = dict(os.environ, KAKAO_DATA_DIR=str(data_dir), PYTHONIOENCODING='utf-8',
                       KAKAO_PUBLIC_BASE_URL='http://192.168.10.20:8080')
            process = subprocess.Popen([sys.executable, str(ROOT / 'backend/serve_local.py'), '--port', str(port)],
                                       cwd=str(ROOT), env=env)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(base + '/api/health', timeout=.5):
                            break
                    except OSError:
                        if process.poll() is not None:
                            self.fail('Backend/model exited during startup')
                        time.sleep(.2)
                else:
                    self.fail('CV backend did not become ready')
                client = Client(base)
                client.signup('Classifier QC', 'classifier')
                _, supplier = client.request('/api/suppliers', 'POST', {'name': 'Pemasok Analisis', 'code': 'CLS'})
                _, draft = client.request('/api/lots', 'POST', {'supplier_id': supplier['id']})
                photo = ROOT / 'backend/tests/images/tray_real_01.jpg'
                upload(client, draft['id'], photo, uuid4().hex)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    listing = client.request(f"/api/drafts/{draft['id']}/photos")[1]
                    item = listing['items'][0]
                    if item['status'] in ('ready', 'warning', 'failed', 'invalid'):
                        break
                    time.sleep(.25)
                self.assertIn(item['status'], ('ready', 'warning'), item)
                expected = item['usable_count']
                version = client.request(f"/api/drafts/{draft['id']}")[1]['input_version']
                self.assertEqual(item['review_state'], 'included')
                status, queued = client.request(f"/api/drafts/{draft['id']}/analyze", 'POST', {
                    'expected_input_version': version, 'confirm_small_sample': True,
                })
                self.assertEqual(status, 202, queued)
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    status, result = client.request(f"/api/drafts/{draft['id']}/result")
                    if result['status'] in ('complete', 'failed'):
                        break
                    time.sleep(.25)
                self.assertEqual(status, 200)
                self.assertEqual(result['status'], 'complete', result)
                self.assertEqual(result['usable_count'], expected)
                data = result['result']
                self.assertEqual(data['usable_count'], expected)
                self.assertEqual(data['counts']['fermented'] + data['counts']['poorly_fermented'], expected)
                self.assertEqual(sum(p['usable_count'] for p in data['photos']), expected)
                image_url = f"{base}/api/runs/{result['id']}/photos/{item['id']}/image"
                request = urllib.request.Request(image_url, headers={'Origin': base})
                with client.opener.open(request, timeout=10) as response:
                    self.assertEqual(response.headers.get_content_type(), 'image/jpeg')
                    self.assertTrue(response.read().startswith(b'\xff\xd8'))
                saved_draft = client.request(f"/api/drafts/{draft['id']}")[1]
                _, replacement = client.request('/api/suppliers', 'POST', {'name': 'Pemasok Koreksi', 'code': 'KOREKSI'})
                status, saved_draft = client.request(f"/api/drafts/{draft['id']}", 'PATCH', {
                    'expected_version': saved_draft['draft_version'], 'supplier_id': replacement['id'],
                    'weight_kg': '42.5', 'notes': 'Penerimaan dari pemasok terdaftar', 'wizard_step': 'result',
                })
                self.assertEqual(status, 200, saved_draft)
                self.assertEqual(saved_draft['selected_run_id'], result['id'])
                self.assertEqual(saved_draft['input_version'], version)
                status, finalized = client.request(f"/api/drafts/{draft['id']}/finalize", 'POST', {
                    'expected_version': saved_draft['draft_version'],
                })
                self.assertEqual(status, 200, finalized)
                self.assertTrue(finalized['human_id'].startswith('KOREKSI-'))
                self.assertEqual(finalized['supplier_name'], 'Pemasok Koreksi')
                self.assertEqual(client.request(f"/api/drafts/{draft['id']}/finalize", 'POST', {
                    'expected_version': saved_draft['draft_version'],
                })[1], finalized)
                status, detail = client.request(f"/api/lots/{finalized['lot_id']}")
                self.assertEqual(status, 200)
                self.assertEqual(detail['analysis']['result'], data)
                self.assertEqual(detail['lot']['weight_kg'], '42.5')
                lot_id = finalized['lot_id']
                first_revision = finalized['revision_id']
                status, report = client.request(f'/api/lots/{lot_id}/revisions/{first_revision}/report', 'POST')
                self.assertEqual(status, 200, report)
                token = report['url'].rsplit('/', 1)[-1]
                self.assertTrue(report['lan_ready'])
                self.assertEqual(report['report']['usable_count'], expected)
                self.assertEqual(report['report']['supplier_name'], 'Pemasok Koreksi')
                self.assertEqual(client.request(f'/api/lots/{lot_id}/revisions/{first_revision}/report', 'POST')[1]['url'], report['url'])
                public = Client(base)
                self.assertEqual(public.request(f'/api/reports/{token}')[1]['report']['revision_number'], 1)
                self.assertEqual(public.request(f'/api/reports/{token}')[1]['report']['usable_count'], expected)
                with public.opener.open(base + f'/api/reports/{token}/photos/{item["id"]}') as response:
                    original_annotation = response.read()
                    self.assertTrue(original_annotation.startswith(b'\xff\xd8'))
                with public.opener.open(base + f'/api/reports/{token}/qr') as response:
                    qr_bytes = response.read()
                    self.assertTrue(qr_bytes.startswith(b'\x89PNG'))
                    import cv2
                    import numpy as np
                    qr_image = cv2.imdecode(np.frombuffer(qr_bytes,dtype=np.uint8),cv2.IMREAD_COLOR)
                    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(qr_image)
                    self.assertEqual(decoded, report['url'])
                self.assertEqual(public.request(f'/api/reports/{token}/photos/' + 'a' * 32)[0], 404)
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    report = public.request(f'/api/reports/{token}')[1]
                    if report['pdf_status'] in ('complete', 'failed'):
                        break
                    time.sleep(.25)
                self.assertEqual(report['pdf_status'], 'complete', report)
                with public.opener.open(base + f'/api/reports/{token}/pdf') as response:
                    pdf = response.read()
                    self.assertTrue(pdf.startswith(b'%PDF-'))
                    self.assertGreater(len(pdf), len(original_annotation))
                version = detail['lot']['lot_version']
                status, working = client.request(f'/api/lots/{lot_id}/revisions', 'POST',
                                                 {'expected_lot_version': version})
                self.assertEqual(status, 200, working)
                self.assertEqual(working['lot_id'], lot_id)
                self.assertEqual(working['base_revision_id'], first_revision)
                self.assertEqual(working['base_revision_number'], 1)
                self.assertEqual(working['next_revision_number'], 2)
                self.assertEqual(working['wizard_step'], 'sample')
                self.assertEqual(client.request(f'/api/lots/{lot_id}/revisions', 'POST',
                                                {'expected_lot_version': version})[1]['id'], working['id'])
                self.assertEqual(client.request(f'/api/drafts/{working["id"]}/photos')[1]['items'][0]['id'], item['id'])
                status, new_photo = upload(client, working['id'],
                                           ROOT / 'backend/tests/images/tray_real_02.jpg', uuid4().hex, item['id'])
                self.assertEqual(status, 200)
                self.assertEqual(client.request(f'/api/lots/{lot_id}/revisions/{first_revision}')[1]['analysis']['result'], data)
                with public.opener.open(base + f'/api/reports/{token}/photos/{item["id"]}') as response:
                    self.assertEqual(response.read(), original_annotation)
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    revised_photos = client.request(f'/api/drafts/{working["id"]}/photos')[1]['items']
                    if revised_photos[0]['status'] in ('ready','warning','invalid','failed'):
                        break
                    time.sleep(.25)
                self.assertIn(revised_photos[0]['status'], ('ready','warning'))
                revised_version = client.request(f'/api/drafts/{working["id"]}')[1]['input_version']
                self.assertEqual(client.request(f'/api/drafts/{working["id"]}/analyze', 'POST', {
                    'expected_input_version': revised_version, 'confirm_small_sample': True})[0], 202)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    revised_result = client.request(f'/api/drafts/{working["id"]}/result')[1]
                    if revised_result['status'] in ('complete','failed'):
                        break
                    time.sleep(.25)
                self.assertEqual(revised_result['status'], 'complete', revised_result)
                self.assertEqual(revised_result['usable_count'], revised_photos[0]['usable_count'])
                ready_draft = client.request(f'/api/drafts/{working["id"]}')[1]
                status, second = client.request(f'/api/drafts/{working["id"]}/finalize', 'POST',
                                                {'expected_version': ready_draft['draft_version']})
                self.assertEqual(status, 200, second)
                self.assertEqual(second['lot_id'], lot_id)
                self.assertEqual(second['revision_number'], 2)
                revisions = client.request(f'/api/lots/{lot_id}/revisions')[1]
                self.assertEqual(len(revisions['items']), 2)
                self.assertEqual(revisions['current_revision_id'], second['revision_id'])
                self.assertEqual(client.request('/api/lots')[1]['items'][0]['revision_number'], 2)
                self.assertEqual(client.request(f'/api/lots/{lot_id}/revisions/{first_revision}/report', 'POST')[1]['url'], report['url'])
                self.assertEqual(public.request(f'/api/reports/{token}')[1]['report']['usable_count'], expected)
                self.assertEqual(client.request(f'/api/lots/{lot_id}/revisions/{first_revision}/activate', 'POST',
                    {'expected_lot_version': revisions['lot_version'] - 1})[0], 409)
                activated = client.request(f'/api/lots/{lot_id}/revisions/{first_revision}/activate', 'POST',
                    {'expected_lot_version': revisions['lot_version']})[1]
                self.assertEqual(activated['current_revision_id'], first_revision)
                self.assertEqual(client.request('/api/lots')[1]['items'][0]['revision_number'], 1)
                self.assertEqual(client.request(f'/api/suppliers/{replacement["id"]}', 'PATCH', {
                    'name': 'Nama pemasok setelah laporan', 'contact': '', 'notes': ''})[0], 200)
                self.assertEqual(public.request(f'/api/reports/{token}')[1]['report']['supplier_name'], 'Pemasok Koreksi')
                fresh = client.request(f'/api/lots/{lot_id}')[1]['lot']
                _, abandoned = client.request(f'/api/lots/{lot_id}/revisions', 'POST', {
                    'expected_lot_version': fresh['lot_version']})
                self.assertEqual(client.request(f'/api/drafts/{abandoned["id"]}/analyze', 'POST', {
                    'expected_input_version': abandoned['input_version'], 'confirm_small_sample': True})[0], 202)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    ready = client.request(f'/api/drafts/{abandoned["id"]}/result')[1]
                    if ready['status'] in ('complete','failed'):
                        break
                    time.sleep(.25)
                self.assertEqual(ready['status'], 'complete', ready)
                active_again = client.request(f'/api/lots/{lot_id}/revisions/{second["revision_id"]}/activate', 'POST',
                    {'expected_lot_version': fresh['lot_version']})[1]
                self.assertEqual(active_again['current_revision_id'], second['revision_id'])
                draft_version = client.request(f'/api/drafts/{abandoned["id"]}')[1]['draft_version']
                self.assertEqual(client.request(f'/api/drafts/{abandoned["id"]}/finalize', 'POST',
                    {'expected_version': draft_version})[0], 409)
                self.assertEqual(client.request(f'/api/drafts/{abandoned["id"]}', 'DELETE')[0], 200)
                with public.opener.open(base + f'/api/reports/{token}/photos/{item["id"]}') as response:
                    self.assertEqual(response.read(), original_annotation)
                other = Client(base)
                other.signup('Other QC', 'otherqc')
                self.assertEqual(other.request(f"/api/lots/{finalized['lot_id']}")[0], 404)
                self.assertEqual(other.request(f'/api/lots/{lot_id}/revisions')[0], 404)
                self.assertEqual(other.request(f'/api/lots/{lot_id}/revisions/{first_revision}/report', 'POST')[0], 404)
                lots = client.request('/api/lots')[1]['items']
                self.assertEqual(len(lots), 1)
                self.assertEqual(lots[0]['human_id'], finalized['human_id'])
                self.assertFalse(lots[0]['eligible'])
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
