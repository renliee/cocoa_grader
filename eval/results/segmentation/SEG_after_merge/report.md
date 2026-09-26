# Segmentation SEG_after_merge (val)

- code: segment.py c68cc41a9e86, config.py 201a43553809
- git: 9709af24fc (dirty), created 2026-09-26 18:52:24 WIB
- expected count: 15 beans per photo
- time: 172.5 ms per photo (segmentation only, this machine)

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
