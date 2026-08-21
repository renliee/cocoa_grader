# Evaluasi biji lokal

Model dilatih pada citra Mendeley (Santos dkk.) yang diambil di studio dengan
latar seragam. Folder ini berisi pengujian model tersebut pada foto cut test
yang diambil sendiri dengan kamera ponsel, kertas biasa, dan cahaya ruangan.

## Isi

```
gate_labels.csv     121 label acuan, dibuat manusia
images/             8 foto asli, masukan apa adanya ke pipeline
images_numbered/    8 foto yang sama dengan nomor biji tercetak
```

## Cara membaca

`gate_labels.csv` berkolom `foto,idx,label`. Kolom `idx` adalah nomor biji
dalam foto tersebut, dimulai dari 0, mengikuti urutan hasil deteksi. Nomor yang
sama tercetak pada gambar di `images_numbered/`, jadi satu baris CSV bisa
ditelusuri ke satu biji.

Label tidak dicetak pada gambar. CSV adalah satu-satunya sumber label.

| foto | jumlah biji | | foto | jumlah biji |
|---|---|---|---|---|
| 107 | 15 | | 46 | 15 |
| 143 | 18 | | campuran | 15 |
| 153 | 18 | | campuran1 | 10 |
| 29 | 20 | | campuran2 | 10 |

Total 121 biji. Jumlah baris per foto di CSV sama dengan angka di atas.

## Cara label dibuat

Pelabelan dikerjakan oleh tiga anggota tim yang belum melihat output model. 
Label akhir ditentukan berdasarkan suara mayoritas, yaitu 2 dari 3 atau 3 dari 3 anggota tim.
Label sudah ditentukan dan diselesaikan sebelum evaluasi model dijalankan.

## Metrik

Komposisi label timpang: 100 `poorly_fermented` dan 21 `fermented`, atau 82.6%
berbanding 17.4%. Pada set seperti ini, program yang selalu menjawab
`poorly_fermented` tanpa membaca gambar sama sekali akan mencetak akurasi
82.6%. 

Karena itu penilaian memakai rata-rata recall kedua kelas, yaitu rata-rata dari
proporsi benar di kelas `fermented` dan proporsi benar di kelas
`poorly_fermented`, disertai recall kelas `fermented` secara terpisah. Ukuran
ini dikenal sebagai balanced accuracy.

Konfigurasi dengan balanced accuracy tertinggi adalah model seimbang dengan latar
hitam dan memiliki rona hijau, 0,777 dengan 15 dari 21 biji fermented terbaca.
Konfigurasi itu yang dipakai di produk akhir. Tabel lengkap enam
konfigurasi beserta dasar pemilihannya ada di proposal.

## Batasan

Delapan foto, satu jenis kertas alas, satu rentang pencahayaan. Angka di sini
menggambarkan perilaku model pada kondisi tersebut, bukan pada seluruh kondisi
lapangan yang bervariasi.