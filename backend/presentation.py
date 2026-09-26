"""English system copy for saved evidence; never rewrite user text or measurements."""
from core import grade, config
from domain import sample_band


def result_copy(payload):
    visible = dict(payload)
    count = payload['usable_count']
    visible['sample_band'] = sample_band(count)
    visible['notes'] = ([f'The sample contains {count} beans, below the cut-test reference of '
                         f'{config.MIN_SAMPLE_FULL}. Percentages are indicative.']
                        if count < config.MIN_SAMPLE_FULL else [])
    summary = {
        'n_terbaca': count, 'n_foto': len(payload['photos']),
        'jumlah': payload['counts'], 'persen': payload['percent_rounded'],
        'catatan': visible['notes'], 'disclaimer': grade.DISCLAIMER,
    }
    visible['disclaimer'] = grade.DISCLAIMER
    if 'report' in payload:
        visible['report'] = grade.format_report(summary)
    return visible


def precheck_warnings(manifest):
    # Rebuild only generated warnings from authoritative saved precheck facts.
    warnings = []
    if not manifest['roi_detected']:
        warnings.append('The paper background could not be identified reliably. Review the boxes on the photo.')
    # Preserve the original fragmentation warning decision, not a new CV threshold.
    if any('serpihan' in text.lower() or 'fragments or excluded areas' in text
           for text in manifest['warnings']):
        warnings.append('Many fragments or excluded areas were detected. Retake this photo.')
    if manifest['excluded_percent'] is not None and manifest['excluded_percent'] > 5:
        warnings.append(f"{manifest['excluded_percent']:.1f}% of detected candidates were excluded.")
    if 0 < manifest['usable_count'] < 5:
        warnings.append('This photo adds only 1–4 usable beans.')
    return warnings
