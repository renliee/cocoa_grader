"""Render a precheck from the same segmentation result used to save bean inputs."""
import cv2

COLORS = {
    'usable': (180, 130, 70),
    'edge_cut': (0, 140, 255),
    'unresolved_cluster': (180, 60, 160),
    'fragment': (0, 190, 230),
    'suspicious_geometry': (100, 150, 230),
}


def render_precheck(result):
    canvas = result.canonical.copy()
    for item in result.objects:
        x, y, w, h = item['bbox']
        color = COLORS['usable' if item['disposition'] == 'usable' else item['reason']]
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 3)
        label = item['id'].replace('obj-', '') if item['disposition'] == 'usable' else item['reason']
        cv2.putText(canvas, label, (x, max(22, y - 7)), cv2.FONT_HERSHEY_SIMPLEX,
                    .55, color, 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError('Could not encode precheck annotation')
    return encoded.tobytes()
