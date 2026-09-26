# Hasil Iterasi I (Fine-Tuning)

Iterasi pertama difokuskan pada masalah paling mendasar yang ditemukan pada baseline, yaitu performa classifier yang masih rendah bahkan pada kondisi canonical. Pada baseline, Balanced Accuracy canonical hanya mencapai 54,9% dan Recall Fermented hanya 9,8%. Karena itu, sebelum mencoba augmentation untuk kondisi tertentu, tim terlebih dahulu menguji apakah model dapat beradaptasi dengan data lokal hanya melalui fine-tuning tanpa augmentation.

Tiga konfigurasi dibandingkan dengan dataset, benchmark, preprocessing, dan skema evaluasi yang sama. Perbedaannya hanya terletak pada bagian model yang dibuka selama fine-tuning: FT_A menggunakan full unfreeze, FT_B hanya melatih classification head, sedangkan FT_C menggunakan partial unfreeze. Dengan cara ini, perubahan hasil dapat dibaca sebagai pengaruh strategi fine-tuning, bukan perubahan kondisi evaluasi.

| **Run** | **Strategi** | **Augmentation** |
|---|---|---|
| FT_A | Full unfreeze | Tidak ada |
| FT_B | Head only | Tidak ada |
| FT_C | Partial unfreeze | Tidak ada |

## Perbandingan Hasil

Tabel berikut membandingkan Balanced Accuracy baseline dengan ketiga hasil fine-tuning pada seluruh variasi validation set.

| **Variant** | **Baseline** | **FT_A** | **FT_B** | **FT_C** |
|---|---:|---:|---:|---:|
| canon | 54,9% | 69,4% | 73,8% | **80,2%** |
| blur | 50,4% | 59,8% | 50,4% | **63,6%** |
| lowl | 53,6% | 50,9% | 54,7% | **59,1%** |
| overx | 43,8% | 49,5% | 49,5% | 44,6% |
| rotate | 44,9% | **69,5%** | 62,6% | 63,5% |
| warm | 50,8% | **64,6%** | 62,4% | 57,4% |
| **ALL** | **49,5%** | **60,3%** | **58,7%** | **61,4%** |

Secara keseluruhan, ketiga konfigurasi menghasilkan perbaikan dibanding baseline. FT_A meningkatkan Balanced Accuracy agregat dari 49,5% menjadi 60,3%, FT_B menjadi 58,7%, dan FT_C menjadi 61,4%. Perbedaan paling jelas terlihat pada canonical: FT_C mencapai 80,2%, naik 25,3 poin persentase dari baseline 54,9%. FT_C juga memberikan hasil terbaik pada blur dan low light.

Perubahan fine-tuning juga terlihat pada keseimbangan antar kelas:

| **Model** | **Recall Fermented** | **Recall Poorly Fermented** | **Balanced Accuracy (ALL)** |
|---|---:|---:|---:|
| Baseline | 20,7% | 78,4% | 49,5% |
| FT_A | 69,8% | 50,9% | 60,3% |
| FT_B | 70,6% | 46,8% | 58,7% |
| **FT_C** | **48,5%** | **74,3%** | **61,4%** |

Baseline sebelumnya sangat jarang mengenali kelas Fermented. Fine-tuning berhasil mengubah pola tersebut, tetapi perilaku antar kelas belum sepenuhnya stabil. FT_A dan FT_B meningkatkan Recall Fermented secara sangat besar, namun diikuti penurunan Recall Poorly Fermented. FT_C tidak menghasilkan Recall Fermented setinggi FT_A/FT_B, tetapi lebih mampu mempertahankan Recall Poorly Fermented dan menghasilkan Balanced Accuracy agregat tertinggi.

Hasil per variasi juga menunjukkan bahwa belum ada satu konfigurasi yang unggul pada semua kondisi. FT_A memberikan skor tertinggi pada rotate (69,5%) dan warm (64,6%), sedangkan FT_C unggul pada canonical (80,2%), blur (63,6%), dan low light (59,1%). Pada overexposed, FT_A dan FT_B mencapai 49,5%, sedangkan FT_C hanya 44,6%. Ini menunjukkan bahwa fine-tuning umum sudah memperbaiki kemampuan model terhadap data lokal, tetapi masalah pada kondisi akuisisi tertentu masih tersisa.

## Keputusan Iterasi I

Untuk eksperimen selanjutnya, tim memilih FT_C (partial unfreeze) sebagai model dasar atau BEST_HYP. Pemilihan ini tidak didasarkan pada satu variasi saja. FT_C memperoleh Balanced Accuracy canonical tertinggi (80,2%) sekaligus Balanced Accuracy agregat tertinggi (61,4%). Karena tujuan Iterasi I adalah memperbaiki kemampuan dasar model terhadap data lokal sebelum menangani ketahanan tertentu, hasil canonical dan performa agregat menjadi pertimbangan utama.

FT_A tetap menunjukkan hasil yang lebih baik pada beberapa variasi, terutama rotate dan warm, tetapi tidak dipilih sebagai model dasar karena kemampuan canonical-nya masih berada di bawah FT_C. FT_B juga meningkatkan canonical secara signifikan, tetapi performa agregatnya paling rendah di antara ketiga hasil fine-tuning. Dengan demikian, strategi partial unfreeze dibekukan untuk eksperimen berikutnya agar perubahan selanjutnya dapat difokuskan pada augmentation, bukan kembali mengubah bagian model yang dilatih.

Masalah yang masih terlihat setelah FT_C adalah:

- **Overexposed** masih menjadi kondisi terlemah dengan Balanced Accuracy 44,6%, hampir tidak berubah dari baseline 43,8%.
- **Warm lighting** masih rendah pada 57,4% dan Recall Fermented hanya 33,3%.
- **Low light** meningkat menjadi 59,1%, tetapi Recall Poorly Fermented hanya 37,9%.
- **Rotation** meningkat cukup besar dari 44,9% menjadi 63,5%, tetapi masih berada jauh di bawah canonical.
- **Blur** meningkat dari 50,4% menjadi 63,6%, tetapi masih menunjukkan perbedaan recall yang besar antar kelas.
