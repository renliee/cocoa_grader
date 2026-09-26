# S0 segmentation (val)

- created: 2026-09-26 09:47:16 WIB
- settings: target_w=1600 pad=4
- git: ddcfe0a35f

| variant | images | recovered / gt | exact images | under | over | MAE | skip rows | flagged | edge | warn |
|---|---|---|---|---|---|---|---|---|---|---|
| canon | 6 | 90/90 | 6 | 0 | 0 | 0.0 | 0 | 0 | 0 | 4 |
| blur | 6 | 90/90 | 6 | 0 | 0 | 0.0 | 0 | 0 | 0 | 3 |
| lowl | 6 | 90/90 | 6 | 0 | 0 | 0.0 | 0 | 0 | 3 | 0 |
| overx | 6 | 88/90 | 5 | 1 | 0 | 0.333 | 0 | 0 | 0 | 5 |
| rotate | 6 | 90/90 | 6 | 0 | 0 | 0.0 | 0 | 0 | 0 | 4 |
| warm | 6 | 90/90 | 6 | 0 | 0 | 0.0 | 0 | 0 | 0 | 4 |
| ALL | 36 | 538/540 | 35 | 1 | 0 | 0.056 | 0 | 0 | 3 | 20 |

## Photos to look at

| photo | gt | detected | flagged | edge | warn |
|---|---|---|---|---|---|
| val_blur_1 | 15 | 15 | 0 | 0 | True |
| val_blur_3 | 15 | 15 | 0 | 0 | True |
| val_blur_6 | 15 | 15 | 0 | 0 | True |
| val_canon_1 | 15 | 15 | 0 | 0 | True |
| val_canon_3 | 15 | 15 | 0 | 0 | True |
| val_canon_4 | 15 | 15 | 0 | 0 | True |
| val_canon_6 | 15 | 15 | 0 | 0 | True |
| val_overx_1 | 15 | 13 | 0 | 0 | True |
| val_overx_2 | 15 | 15 | 0 | 0 | True |
| val_overx_3 | 15 | 15 | 0 | 0 | True |
| val_overx_4 | 15 | 15 | 0 | 0 | True |
| val_overx_6 | 15 | 15 | 0 | 0 | True |
| val_rotate_1 | 15 | 15 | 0 | 0 | True |
| val_rotate_3 | 15 | 15 | 0 | 0 | True |
| val_rotate_4 | 15 | 15 | 0 | 0 | True |
| val_rotate_6 | 15 | 15 | 0 | 0 | True |
| val_warm_3 | 15 | 15 | 0 | 0 | True |
| val_warm_4 | 15 | 15 | 0 | 0 | True |
| val_warm_5 | 15 | 15 | 0 | 0 | True |
| val_warm_6 | 15 | 15 | 0 | 0 | True |

skip rows = detections the labellers marked as dust or merged beans (only known for the frozen settings).
