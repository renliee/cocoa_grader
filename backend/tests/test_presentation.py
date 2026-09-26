import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presentation import result_copy, precheck_warnings


class PresentationTests(unittest.TestCase):
    def test_saved_evidence_is_not_mutated_or_recalculated(self):
        payload = {
            'usable_count': 16, 'counts': {'fermented': 3, 'poorly_fermented': 13},
            'percent_rounded': {'fermented': 19, 'poorly_fermented': 81},
            'sample_band': {'label': 'Sangat terbatas'}, 'notes': ['Sampel kecil'],
            'disclaimer': 'Hasil indikatif', 'report': 'Laporan lama',
            'photos': [{'annotation_sha256': 'unchanged'}],
            'lot_notes': 'Sampel dari Pak Ahmad', 'supplier_name': 'Pak Ahmad',
        }
        original = copy.deepcopy(payload)
        displayed = result_copy(payload)
        self.assertEqual(payload, original)
        self.assertEqual(displayed['sample_band']['label'], 'Very limited')
        self.assertIn('16 beans analyzed', displayed['report'])
        for key in ('counts', 'percent_rounded', 'photos', 'lot_notes', 'supplier_name'):
            self.assertEqual(displayed[key], original[key])

    def test_empty_precheck_has_no_percentage_warning(self):
        self.assertEqual(precheck_warnings({'roi_detected': True, 'warnings': [],
                         'excluded_percent': None, 'usable_count': 0}), [])

    def test_legacy_precheck_warnings_use_saved_facts(self):
        warnings = precheck_warnings({'roi_detected': False, 'warnings': ['Banyak serpihan'],
                    'excluded_percent': 25.5, 'usable_count': 4})
        self.assertEqual(len(warnings), 4)
        self.assertIn('25.5%', warnings[2])
        self.assertIn('1–4 usable beans', warnings[3])
