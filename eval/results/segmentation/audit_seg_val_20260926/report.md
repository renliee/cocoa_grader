# Segmentation audit_seg_val_20260926 (val)

- code: segment.py 9248dacdc0ff, config.py ab2a90e64274
- git: ddcfe0a35f, created 2026-09-26 12:34:12 WIB
- expected count: 15 beans per photo
- time: 175.3 ms per photo (segmentation only, this machine)

| variant | photos | detected / expected | photos exact |
|---|---|---|---|
| canon | 6 | 90/90 | 6/6 |
| blur | 6 | 90/90 | 6/6 |
| lowl | 6 | 90/90 | 6/6 |
| overx | 6 | 88/90 | 5/6 |
| rotate | 6 | 90/90 | 6/6 |
| warm | 6 | 90/90 | 6/6 |
| ALL | 36 | 538/540 | 35/36 |

## Photos where detected != expected

| photo | detected / expected |
|---|---|
| val_overx_1 | 13/15 |
