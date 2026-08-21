# KakaoLens

Menghitung komposisi tingkat fermentasi satu lot biji kakao dari foto hasil *cut test*.

Pengguna sasaran adalah tengkulak, titik pengumpulan pertama antara petani dan industri
cokelat. Satu atau beberapa foto diunggah, tiap biji pada foto dipisahkan lalu
diklasifikasi ke salah satu dari dua kelas: **Terfermentasi baik** atau
**Kurang terfermentasi**. Hasilnya dilaporkan sebagai proporsi lot, bukan vonis per biji.

Sistem melaporkan indikasi, bukan vonis mutu, dan hanya menilai tingkat fermentasi.
Parameter mutu lain seperti biji berjamur, berserangga, kotoran, atau berkecambah tidak
dinilai. Biji yang terdeteksi tapi gagal dibaca selalu dilaporkan jumlahnya, tidak
dibuang diam diam.

## Langkah dalam menjalankan program 

Kami menggunakan Docker dan Docker Compose. Tidak perlu Python, GPU, atau install manual.

```bash
git clone https://github.com/renliee/cocoa_grader.git
cd cocoa_grader
docker compose up --build -d
```

Buka `http://localhost:8080`.   

Build untuk pertama kalinya memakan waktu beberapa menit karena memasang PyTorch versi CPU. Kontainer
frontend sengaja menunggu backend lolos healthcheck sebelum dijalankan, jadi halaman baru
bisa dibuka setelah model selesai dimuat. 

Memantau prosesnya :

```bash
docker compose logs -f backend
```

Backend mencatat tiap tahap ke stdout: model yang dimuat beserta nama kelasnya saat
startup, lalu per permintaan berupa nama tiap foto, durasi segmentasi dan klasifikasi,
serta hitungan biji dari masing masing tahap. Angkanya sama dengan yang tampil di
halaman. Permintaan healthcheck tidak ikut dicatat supaya log tidak tenggelam oleh baris
berulang tiap 10 detik.

Menghentikan:

```bash
docker compose down
```

Backend dapat diakses melalui `http://localhost:8000`, dengan dokumentasi API
interaktif di `http://localhost:8000/docs`.

## Arsitektur 

Terbagi menjadi 3 lapis terpisah, masing masing dengan tanggung jawab tunggal :

```
frontend/          HTML, CSS, JS vanilla, dijalankan dengan nginx
backend/main.py    HTTP layers, satu satunya file yang mengimpor FastAPI
backend/core/      pipeline utama, bebas framework
```

`ml/` tidak termasuk di dalamnya. Isinya notebook pelatihan dan bukti evaluasi, tidak ikut
ke dalam image Docker dan tidak dipanggil saat inferensi.

`backend/core/` tidak mengimpor FastAPI sama sekali. Setiap modul di dalamnya bisa
dijalankan langsung dari terminal untuk diperiksa terpisah dari server:

```bash
cd backend
python core/segment.py tests/images/tray_real_01.jpg
python core/classify.py weights/best.pt crops/
```

Kemudian `segment.py` akan menghasilkan `<nama>_vis.jpg` (kotak bernomor per biji), `<nama>_mask.jpg`
(mask biner), dan folder `crops/` berisi potongan tiap biji. `classify.py` kemudian
akan membaca folder itu.

nginx menampilkan `index.html` secara statis dan meneruskan `/api/` ke kontainer backend.
Batas waktu proxy dinaikkan ke 300 detik karena segmentasi dan klasifikasi puluhan biji
di CPU tidak selesai dalam batas normal bawaan nginx.

## Alur pipeline

1. **`segment.py`** memisahkan biji dari alas (kertas putih) menggunakan OpenCV classic: deteksi kertas
   alas, jarak warna Lab terhadap latar, ambang median + MAD, lalu watershed per gumpalan
   untuk memisahkan biji yang bersentuhan. Deterministik, tidak ada model terlatih di
   tahap ini.
2. **`classify.py`** mengklasifikasi setiap potongan biji dengan model YOLO11n-cls.
   Sebelum diklasifikasi, tiap potongan diproses melalui tiga langkah. Pertama, area di luar bentuk biji 
   diubah jadi hitam. Potongan hasil segmentasi masih menyisakan kertas alas di pojoknya, terukur 28,6% 
   sampai 37,6% dari tiap potongan, sedangkan pada posisi yang sama di data latih selalu hitam. Karena 
   model memproses seluruh isi potongan, bagian kertas itu ikut memengaruhi hasil klasifikasi.
   Kedua, potongan yang bentuknya memanjang diberi bingkai hitam di sisi pendeknya sampai berbentuk persegi, 
   karena YOLO memotong bagian tengah gambar sebelum memprosesnya, jika tidak dipersegikan, ujung ujung 
   biji akan ikut terpotong. Ketiga, channel hijau dikalikan dengan gain tetap untuk mendekatkan warna foto ke kondisi data latih.
3. **`grade.py`** menghitung jumlah dan persentase per kelas, serta menyusun catatan
   kalau ukuran sampel kecil atau jika ada biji yang tidak terbaca.

Segmentasi dan klasifikasi adalah dua tahap terpisah. YOLO11n-cls adalah pengklasifikasi,
bukan detektor biji kakao, sehingga bukan YOLO11n-cls yang menghasilkan kotak pembatas.

## Endpoint

### `POST /api/analyze`

Multipart, field `files`, satu atau beberapa berkas gambar.
Maksimal 40 berkas per permintaan, maksimal 10 MB per berkas.

Bentuk respons:

```jsonc
{
  "ringkasan": {
    "n_terbaca": 121,
    "n_foto": 8,
    "n_tidak_terbaca": 9,
    "jumlah":  {"fermented": 21, "poorly_fermented": 100},
    "persen":  {"fermented": 17, "poorly_fermented": 83},
    "catatan": ["..."],
    "disclaimer": "..."
  },
  "laporan": "versi teks polos",
  "per_foto": [
    {
      "nama": "foto1.jpg",
      "biji_terbaca": 15,
      "biji_tidak_terbaca": 2,
      "gumpalan": 0,
      "serpihan": 0,
      "kena_tepi": 2,
      "luas_terbuang": 0.0,
      "segmentasi_curiga": false,
      "jumlah_kelas": {"fermented": 2, "poorly_fermented": 13},
      "gambar": "<JPEG base64, tanpa awalan data URI>"
    }
  ],
  "blocking_warning": []
}
```

Label ditampilkan sebagai "Terfermentasi baik" dan "Kurang terfermentasi".
Nilai internalnya adalah `fermented` dan `poorly_fermented`.

`per_foto[].gambar` adalah foto yang sudah diberi kotak dan label, digambar dari pass
deteksi yang sama dengan yang menghasilkan angkanya, jadi gambar dan hitungan tidak
mungkin berbeda. Gumpalan biji yang gagal dipisahkan tidak dibuang dari hitungan, jumlahnya dilaporkan
sebagai peringatan di bawah foto yang bersangkutan.

Kode 422 dikembalikan kalau tidak ada satu pun biji terbaca di seluruh foto, karena
kertas kosong dan deteksi yang gagal terlihat sama di angka total.

### `GET /api/health`

Melaporkan apakah model sudah dimuat. Dipakai healthcheck Docker Compose.

## Model

`backend/weights/best.pt` adalah pengklasifikasi biner YOLO11n-cls, dilatih pada dataset
Mendeley `pcx7mj68yn` (Santos dkk.), varian `framed_and_centralized`. Delapan dari 14
folder dipakai, 800 citra.

Alur pelatihan, perbandingan komposisi data latih, dan batasan angkanya ada di
`ml/cocoa.ipynb`.

`ml/gate/` berisi evaluasi model pada 8 foto biji lokal: 121 label acuan, foto aslinya,
dan salinan bernomor supaya tiap baris label bisa ditelusuri ke biji yang dimaksud.
Label dikunci sebelum prediksi model dilihat. Rinciannya ada di `ml/gate/README.md`.

Bobot bisa diganti lewat variabel lingkungan docker `KAKAO_WEIGHTS`. Model dimuat sekali saat
startup, bukan per permintaan, dan nama kelasnya diperiksa terhadap `config.CLASS_NAMES`
saat itu juga. Ketidakcocokan urutan kelas menghentikan proses startup, bukan menghasilkan
angka yang salah diam diam.


## Struktur folder

```
backend/
  main.py              HTTP FastAPI layers
  core/
    config.py          konstanta pipeline
    segment.py         pemisahan biji dari alas dengan OpenCV
    classify.py        wrapper dari YOLO11n-cls
    grade.py           penghitungan komposisi
  weights/best.pt      bobot model
  tests/images/        foto uji
  requirements.txt
  Dockerfile
frontend/
  index.html           seluruh User Interface, HTML/CSS/JS vanilla 
  nginx.conf           penyajian statis dan proxy ke backend
  Dockerfile
ml/
  cocoa.ipynb          notebook training
  gate/
    README.md          cara membaca evaluasi biji lokal
    gate_labels.csv    121 label acuan
    images/            8 foto asli
    images_numbered/   8 foto yang sama dengan nomor biji
docker-compose.yml
```

## Catatan teknis

1. PyTorch dipasang dari indeks CPU di Dockerfile, bukan lewat `requirements.txt`, agar image
tidak membawa dependency CUDA yang tidak diperlukan.

2. `requirements.txt` memakai `opencv-python`, bukan versi headless. `ultralytics` bergantung
pada varian non headless, dan memasang dua duanya bersamaan membuat dua package menulis ke directory
`cv2/` yang sama.

3. Konstanta di `config.py` diberi tag `SWEPT`, `REASONED`, dan `UNVALIDATED`.
agar pembaca bisa membedakan nilai yang sudah diuji dari nilai yang masih dugaan.

4. Timestamp pada log backend ditulis dalam WIB dengan offset tetap UTC+7, bukan mengikuti
zona waktu kontainer.