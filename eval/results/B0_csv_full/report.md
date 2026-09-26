# B0_csv_full (val)

- source: model backend/weights/best.pt sha256 3165f4496810
- preprocessing: P0 {'mask': True, 'g_gain': None} gain=1.24 pad_mode=black
- benchmark: S0_csv_full (1063 beans, labels sha256 753c4b4bca56)
- created: 2026-09-26 10:29:35 WIB
- git: ddcfe0a35f
- timing: 4.9 ms per bean (crop prep + predict, this machine)

| variant | beans | F recall | PF recall | BA | vs canon: broken / fixed / lost | confident wrong |
|---|---|---|---|---|---|---|
| canon | 90 | 6/61 (0.10) | 29/29 (1.00) | 0.549 | - | 38 |
| blur | 90 | 32/61 (0.52) | 14/29 (0.48) | 0.504 | - | 12 |
| lowl | 90 | 17/61 (0.28) | 23/29 (0.79) | 0.536 | - | 12 |
| overx | 88 | 13/59 (0.22) | 19/29 (0.66) | 0.438 | - | 28 |
| rotate | 90 | 7/62 (0.11) | 22/28 (0.79) | 0.449 | - | 44 |
| warm | 90 | 1/63 (0.02) | 27/27 (1.00) | 0.508 | - | 47 |
| ALL | 538 | 76/367 (0.21) | 134/171 (0.78) | 0.495 | - | 181 |

## Weakness candidates (auto, rules in eval/settings.py)

- Clean photos (canon): fermented 6/61 (0.10), poorly fermented 29/29 (1.00).
- Noise floor: on canon, 1 fermented bean = 1.6 pp of F recall, 1 poorly fermented bean = 3.4 pp of PF recall.

## Most confident mistakes

| photo | idx | label | pred | conf |
|---|---|---|---|---|
| val_canon_2 | 7 | fermented | poorly_fermented | 1.0 |
| val_rotate_3 | 7 | fermented | poorly_fermented | 1.0 |
| val_rotate_5 | 9 | fermented | poorly_fermented | 1.0 |
| val_rotate_5 | 11 | fermented | poorly_fermented | 1.0 |
| val_rotate_5 | 12 | fermented | poorly_fermented | 1.0 |
| val_warm_1 | 8 | fermented | poorly_fermented | 1.0 |
| val_warm_1 | 10 | fermented | poorly_fermented | 1.0 |
| val_warm_4 | 9 | fermented | poorly_fermented | 1.0 |
| val_warm_5 | 8 | fermented | poorly_fermented | 1.0 |
| val_canon_1 | 10 | fermented | poorly_fermented | 0.9999 |
| val_rotate_3 | 8 | fermented | poorly_fermented | 0.9999 |
| val_rotate_3 | 9 | fermented | poorly_fermented | 0.9999 |
| val_rotate_3 | 10 | fermented | poorly_fermented | 0.9999 |
| val_rotate_6 | 7 | fermented | poorly_fermented | 0.9999 |
| val_warm_1 | 5 | fermented | poorly_fermented | 0.9999 |
