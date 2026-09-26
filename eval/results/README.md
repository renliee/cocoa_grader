# Peta hasil evaluasi

Empat folder ini adalah titik awal yang perlu dibaca:

| Folder | Peran | Hasil utama |
|---|---|---|
| `S0/` | Baseline segmentasi fase I | 538/540 biji pada `val` |
| `B0_csv_full/` | Baseline klasifikasi fase I | 538 biji; F 76/367; PF 134/171; BA 0.4954 |
| `segmentation/audit_seg_val_20260926/` | Regresi runner baru | 538/540 biji pada `val` |
| `classification/audit_before_val_20260926/` | Regresi bobot `before` melalui runner baru | Sama persis dengan 538 prediksi `B0_csv_full` |

Untuk segmentasi, baca `summary.csv` dan `per_photo.csv`. Untuk klasifikasi, baca `report.md`
untuk metrik per varian, `predictions.csv` untuk hasil per biji, dan `failures.csv` untuk kesalahan.
`run_config.json` menyimpan hash bobot, manifest, label, dan kode; `code_snapshot/` menyimpan salinan
kode backend. `index.csv` mencatat run dari runner baru. CLI tidak mencetak hasil run yang sukses ke terminal.

Belum ada run pada split `test`, run API OpenAI/Gemini/model open source, atau run bobot fine-tune baru.
Untuk lima model pembanding, sediakan ID model dan kredensial/endpoint asli serta path bobot fine-tune
jika tersedia. Coba API pada 20 biji `val`, periksa prediksi dan failure, lalu lanjutkan `val` penuh.
Pakai `test` hanya setelah model dan parameter dipilih.
