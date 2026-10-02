# Riset Komunitas — Masalah Delegasi pada Personal AI

- **Status:** temuan awal, belum divalidasi langsung dengan calon pengguna
- **Diperiksa:** 2 Oktober 2026
- **Metode:** penelusuran issue GitHub (termasuk komentar dan PR terkait), thread Hacker News,
  dan forum Obsidian
- **Cakupan:** 13 issue dari 5 proyek + 3 thread Hacker News + 3 thread forum Obsidian

> **Catatan pembacaan.** Temuan ini adalah bukti kualitatif adanya masalah: laporan dari orang
> yang terdorong menulis laporan publik. Dokumen ini **belum mengukur frekuensi atau besarnya
> masalah pada populasi pengguna** — itu bagian dari rencana validasi di bagian akhir.

## Ringkasan eksekutif

**Kandidat masalah:**

> Pengguna masih harus mengawasi asisten AI untuk memastikan konteksnya benar, tugasnya
> berjalan, dan hasilnya benar-benar tersedia.

**Arah proyek yang direkomendasikan:**

> Pengguna personal AI yang mendelegasikan pekerjaan berulang melalui percakapan membutuhkan
> cara untuk menjaga instruksi tetap mutakhir dan mengetahui hasil aktual setiap tugas, dengan
> pemeriksaan manual yang minimal.

## 1. Masalah nyata yang muncul di komunitas

### A. Informasi sudah tersimpan, tetapi AI menggunakan versi yang keliru

**Bukti pertama — Mem0 [#4956](https://github.com/mem0ai/mem0/issues/4956)** (dibuka 24 April
2026; status saat diperiksa: terbuka)

Skenario yang dilaporkan:

- Pengguna sebelumnya bekerja di perusahaan A.
- Pengguna kemudian menyatakan pindah ke perusahaan B.
- Kedua fakta tersimpan.
- Pencarian tentang pekerjaan saat ini masih dapat memunculkan perusahaan A.

Pengguna lain di thread yang sama melaporkan pengalaman serupa pada penggunaan produksi.

**Bukti kedua — Mem0 [#5063](https://github.com/mem0ai/mem0/issues/5063)** (ditutup sebagai
*not planned*)

Pelapor mencoba menyaring memori berdasarkan kategori dan masa berlaku, lalu memutuskan
**menonaktifkan plugin memori** untuk penggunaan pribadinya:

> "the recall noise was harming more than helping in our specific single-user setup"

**Makna bagi pengguna:** pengguna harus terus mengoreksi informasi yang seharusnya sudah
diperbarui.

**Dugaan penyebab:** relevansi terhadap pertanyaan, waktu berlakunya informasi, dan sumber
informasi belum dibedakan dengan baik.

**Implikasi untuk kita:** menambah jumlah memori tidak otomatis memperbaiki bantuan AI.

### B. Status "berhasil" tidak selalu berarti tujuan pengguna tercapai

**Bukti pertama — OpenClaw [#44925](https://github.com/openclaw/openclaw/issues/44925)**
(dibuka 13 Maret 2026; terbuka, dengan laporan lanjutan hingga September 2026)

Kegagalan yang tercatat dalam thread:

- Tugas selesai pada subagent, tetapi hasil tidak sampai ke pengguna.
- Tugas berhenti tanpa pemberitahuan; pengguna baru tahu setelah bertanya sendiri.
- Agent mengklaim telah membuat berkas, tetapi berkas tersebut tidak ditemukan.

Seorang anggota proyek menjelaskan bahwa perbaikan yang digabung pada September 2026
menyelesaikan sebagian persoalan status tugas, tetapi secara eksplisit menyatakan perbaikan
itu **belum membuktikan seluruh hasil tersampaikan atau berkas yang diklaim benar-benar ada**.

**Bukti kedua — Hermes Agent [#112712](https://github.com/NousResearch/hermes-agent/issues/112712)**
(dibuka 16 September 2026; terbuka)

Kasus konkret: tugas harian berhasil dikerjakan, tetapi topik Telegram tujuan sudah dihapus.
Kegagalan pengiriman tercatat di sistem, namun operator baru mengetahuinya melalui pemantauan
tambahan yang ia buat sendiri.

**Makna bagi pengguna:** pengguna tetap harus menjadi pemeriksa penyelesaian tugas.

**Dugaan penyebab:** sistem memperlakukan tahap-tahap berikut terlalu dekat:

```text
Permintaan diterima
→ proses berjalan
→ proses selesai
→ hasil tersedia
→ hasil dikirim
→ tujuan pengguna terpenuhi
```

Setiap tahap membutuhkan bukti yang berbeda.

### C. Sistem terlihat normal ketika kemampuan pentingnya sudah gagal

**Bukti — Hermes Agent [#49200](https://github.com/NousResearch/hermes-agent/issues/49200)**
(dibuka 19 Juni 2026; terbuka saat diperiksa)

Menurut pelapor:

- Pembaruan container merusak pemuatan penyedia memori.
- Agent beralih ke memori bawaan yang kapasitasnya lebih kecil.
- Percakapan tetap terlihat normal.
- Masalah baru diketahui sekitar **enam hari kemudian**.
- Pelapor akhirnya membangun pemeriksaan kesehatan tambahan.

Angka enam hari adalah pengalaman pelapor tersebut, bukan rata-rata seluruh pengguna.

**Kasus terkait yang sudah diperbaiki:** Hermes Agent
[#47202](https://github.com/NousResearch/hermes-agent/issues/47202) — pesan yang belum
disimpan hilang ketika sesi dikompresi; [PR #48584](https://github.com/NousResearch/hermes-agent/pull/48584)
digabung pada 18 Juni 2026.

**Makna bagi pengguna:** sulit mengetahui kapan bantuan AI masih dapat diandalkan.

**Dugaan penyebab:** kesehatan percakapan, penyimpanan memori, dan pelaksanaan tugas tidak
selalu terlihat sebagai keadaan yang terpisah.

### D. Merawat "second brain" bisa menjadi pekerjaan tambahan

Bukti dari komunitas pengguna (di luar laporan bug developer):

- [Forum Obsidian: "How do you measure whether a system is good?"](https://forum.obsidian.md/t/how-do-you-measure-whether-a-system-is-good/71832)
  — pengguna mempertanyakan manfaat dari terus mengumpulkan, menghubungkan, dan mengatur
  informasi; pengguna lain mengeluhkan kelelahan mengambil keputusan karena mencoba
  mengoptimalkan organisasinya.
- [Forum Obsidian: "A maintainable second brain for someone with ADHD"](https://forum.obsidian.md/t/a-maintainable-second-braind-for-someone-with-adhd/36106)
  — beberapa peserta memilih penggunaan yang lebih sederhana karena waktu yang dihabiskan
  untuk mengatur plugin dan struktur dinilai terlalu besar.
- [Hacker News (Januari 2026)](https://news.ycombinator.com/item?id=46760586) — keluhan
  searah tentang setup personal AI yang "tedious".

**Catatan konteks:** thread forum tersebut berasal dari 2022–2023. Berguna sebagai riwayat
kebutuhan pengguna, bukan bukti kondisi fitur terbaru.

**Makna bagi pengguna:** sistem bantuan bisa menambah pekerjaan pengaturan, pemeliharaan, dan
pemeriksaan.

**Implikasi desain:** manfaat bersih harus memperhitungkan waktu yang dihabiskan untuk
mengurus asistennya.

## 2. Apakah orang benar-benar membutuhkan delegasi semacam ini?

Ada indikasi kebutuhan dan manfaat, meskipun masih berupa pengalaman individual.

### Kebutuhan yang dinyatakan dengan jelas

Seorang pengguna yang mencoba Martin menginginkan asisten untuk melakukan riset, mengatur
pertemuan, dan berkomunikasi, lalu:

> "let me know when it is arranged, or if it's given up."

Dalam [laporannya di Hacker News](https://news.ycombinator.com/item?id=41121880), ia mengalami
konfirmasi pertemuan tanpa hasil yang dapat ditemukan dan akhirnya menyatakan akan membatalkan
trial. Pendiri produk [menanggapi keterbatasan integrasinya](https://news.ycombinator.com/item?id=41122183).

**Catatan:** pengalaman ini dari Juli 2024; tidak digunakan untuk menyimpulkan kualitas Martin
saat ini.

**Kebutuhan yang terlihat cukup jelas: pengguna ingin mengetahui hasil akhir, termasuk ketika
tugas tidak dapat diselesaikan.**

### Ada juga pengalaman positif

Dalam [thread Clawdbot (Januari 2026)](https://news.ycombinator.com/item?id=46760589), seorang
pengguna menceritakan bantuan menyaring calon penyewa dan menjadwalkan kunjungan apartemen;
ia melaporkan penghematan beberapa jam. Pengguna lain menjelaskan manfaat
[ringkasan jadwal keluarga setiap pagi](https://news.ycombinator.com/item?id=46761513).

**Artinya:** ada alur kerja konkret yang dinilai berguna. Kualitas pelaksanaan dan kebutuhan
pengawasannya menjadi pertanyaan penting.

## 3. Kesimpulan akar masalahnya

Temuan ini menunjukkan **beberapa penyebab berbeda**. Memori kedaluwarsa, pengiriman gagal,
dan setup yang merepotkan membutuhkan penanganan masing-masing. Namun semuanya dapat
berkontribusi pada satu masalah pengguna:

> **Pengguna belum dapat menyerahkan suatu komitmen kepada asisten AI tanpa tetap menanggung
> pekerjaan untuk mengingat konteks, memeriksa kemajuan, dan memastikan penyelesaiannya.**

Peta sebab–akibat sementara:

```text
Informasi lama dan baru sulit dibedakan ──→ Pengguna mengoreksi konteks
                                              │
Status proses tidak terikat bukti hasil ──→ Pengguna memeriksa hasil
                                              │
Kegagalan tidak terlihat tepat waktu ─────→ Pengguna mengejar kabar
                                              │
Pemeliharaan sistem terlalu menuntut ─────→ Pengguna mengurus asistennya
                                              │
                                              ▼
                          BEBAN PENGAWASAN TETAP TINGGI
                                              │
                                              ▼
                     Manfaat delegasi berkurang, kepercayaan turun
```

> **Peringatan:** hubungan tersebut adalah sintesis atas laporan komunitas, bukan hasil studi
> terkontrol. Masih perlu diuji langsung pada calon pengguna.

## 4. Arah proyek yang paling layak diprioritaskan

| Kandidat | Dukungan temuan | Pertimbangan |
|---|---|---|
| **Asisten tindak lanjut pribadi yang dapat diverifikasi** | Keluhan status, hasil, dan kegagalan muncul di beberapa sistem | Bisa diuji melalui satu alur kerja lengkap |
| Memori pribadi yang mengikuti perubahan fakta | Kasus teknisnya konkret | Sudah banyak solusi dan penelitian terkait |
| Otomatisasi pengelolaan second brain | Ada keluhan pengguna tentang beban pemeliharaan | Manfaatnya sangat bergantung kebiasaan individu |

**Rekomendasi:** prioritaskan kandidat pertama, dengan memori yang mengikuti perubahan sebagai
salah satu mekanisme pendukung.

**Rumusan masalah awal (kandidat untuk dikunci):**

> Pengguna personal AI yang mendelegasikan pekerjaan berulang melalui percakapan membutuhkan
> cara untuk menjaga instruksi tetap mutakhir dan mengetahui hasil aktual setiap tugas, dengan
> pemeriksaan manual yang minimal.

**Target awal yang masuk akal untuk validasi:** pengguna personal AI yang sudah mencoba
mendelegasikan pekerjaan nyata — mereka bisa membandingkan pengalaman sebelum dan sesudah
secara konkret.

## 5. Mekanisme pemersatu untuk Mitra

Unit utama yang dikelola adalah **komitmen pengguna**:

```text
Komitmen
├─ Tujuan dan kriteria selesai
├─ Instruksi yang masih berlaku
├─ Sumber serta riwayat perubahan
├─ Keadaan pelaksanaan
├─ Bukti hasil
└─ Tindak lanjut jika terhambat
```

Contoh alur yang bisa diuji:

1. Pengguna meminta ringkasan proyek dikirim Jumat.
2. Kamis, pengguna mengubah cakupan dan waktunya.
3. Asisten menggunakan instruksi yang diperbarui.
4. Hasil diperiksa terhadap kriteria yang sudah ditentukan.
5. Pengiriman dicatat berdasarkan respons layanan tujuan.
6. Jika terhambat, pengguna mendapat keadaan yang jelas dan langkah pemulihannya.

> **Catatan:** "diterima layanan Telegram" belum membuktikan "pesan sudah dibaca pengguna".
> Keduanya adalah tingkat bukti yang berbeda.

Setiap cabang masalah mendapat mekanisme yang dapat diperiksa:

| Masalah | Mekanisme |
|---|---|
| Instruksi lama terbawa | Riwayat perubahan dan keputusan aktif |
| Klaim selesai tanpa hasil | Pemeriksaan hasil terhadap kriteria selesai |
| Hasil gagal disampaikan | Status pengiriman yang terpisah |
| Pengguna harus terus bertanya | Pemberitahuan perubahan keadaan yang relevan |
| Terlalu banyak pekerjaan administrasi | Pembaruan melalui percakapan dan pemeriksaan terarah |

## 6. Pembeda yang masih harus dibuktikan

Pembanding yang serius sudah ada:

- [Graphiti](https://github.com/getzep/graphiti) — fakta dengan masa berlaku (validity window),
  pembatalan otomatis, dan keterkaitan ke sumber (provenance).
- NVIDIA — [contoh memory-driven Chief of Staff](https://developer.nvidia.com/blog/building-a-memory-driven-agent-with-nvidia-nemoclaw/).
- OpenClaw dan Hermes Agent — terus memperbaiki pelaksanaan serta pengiriman hasil.

Karena itu, **memori, scheduler, dan riwayat tindakan saja belum cukup menjadi pembeda**.

Klaim yang layak diuji untuk Mitra:

> **Dalam alur kerja tertentu, pengguna membutuhkan lebih sedikit pemeriksaan manual untuk
> memperoleh hasil yang benar dan sesuai instruksi terbaru.**

Ukuran keberhasilan:

- jumlah intervensi manual per tugas;
- penggunaan instruksi yang sudah kedaluwarsa;
- klaim selesai yang tidak didukung hasil;
- waktu sampai pengguna mengetahui kegagalan;
- penghematan waktu setelah dikurangi waktu pemeriksaan dan pemeliharaan.

## 7. Daftar sumber (status diperiksa 2 Oktober 2026)

### Issue GitHub

| Sumber | Proyek | Status | Catatan |
|---|---|---|---|
| [#4956](https://github.com/mem0ai/mem0/issues/4956) | Mem0 | Terbuka | Fakta kedaluwarsa menang atas fakta terbaru |
| [#5063](https://github.com/mem0ai/mem0/issues/5063) | Mem0 | Ditutup (not planned) | Pelapor menonaktifkan plugin memori |
| [#49200](https://github.com/NousResearch/hermes-agent/issues/49200) | Hermes | Terbuka | Fallback memori senyap; ~6 hari tak terdeteksi |
| [#47202](https://github.com/NousResearch/hermes-agent/issues/47202) | Hermes | Ditutup (completed) | Diperbaiki oleh PR #48584 (18 Jun 2026) |
| [#112712](https://github.com/NousResearch/hermes-agent/issues/112712) | Hermes | Terbuka | Kegagalan pengiriman hasil yang tidak terlihat |
| [#44925](https://github.com/openclaw/openclaw/issues/44925) | OpenClaw | Terbuka | Hasil subagent hilang; klaim berkas tanpa bukti |
| [#8298](https://github.com/openclaw/openclaw/issues/8298) | OpenClaw | Ditutup (completed) | Reminder gagal senyap; diperbaiki oleh PR #11641 |
| [#52972](https://github.com/openclaw/openclaw/issues/52972) | OpenClaw | Ditutup (completed) | Catatan "tidak menjadwalkan reminder" yang kontradiktif |
| [#8209](https://github.com/anthropics/claude-code/issues/8209) | Claude Code | Ditutup (duplicate) | Pola kerja prosedural dilupakan; detail sesaat diingat |
| [#85677](https://github.com/anthropics/claude-code/issues/85677) | Claude Code | Terbuka | Dua catatan memori bertabrakan; yang salah menang |
| [#22323](https://github.com/google-gemini/gemini-cli/issues/22323) | Gemini CLI | Terbuka | Batas giliran dilaporkan sebagai sukses ("phantom completion") |

### PR terkait

| Sumber | Proyek | Status |
|---|---|---|
| [#5218](https://github.com/mem0ai/mem0/pull/5218) | Mem0 | Terbuka (conflict) |
| [#7301](https://github.com/mem0ai/mem0/pull/7301) | Mem0 | Ditutup tanpa merge |
| [#48584](https://github.com/NousResearch/hermes-agent/pull/48584) | Hermes | Merged 18 Jun 2026 |
| [#112746](https://github.com/NousResearch/hermes-agent/pull/112746) | Hermes | Terbuka |
| [#112749](https://github.com/NousResearch/hermes-agent/pull/112749) | Hermes | Terbuka |
| [#11641](https://github.com/openclaw/openclaw/pull/11641) | OpenClaw | Merged 8 Feb 2026 |

### Hacker News

| Sumber | Tanggal | Dipakai untuk |
|---|---|---|
| [item 41121880](https://news.ycombinator.com/item?id=41121880) | Jul 2024 | Kebutuhan "beri tahu saat berhasil atau menyerah" |
| [item 41122183](https://news.ycombinator.com/item?id=41122183) | Jul 2024 | Tanggapan pendiri soal keterbatasan integrasi |
| [item 46760237](https://news.ycombinator.com/item?id=46760237) | Jan 2026 | 405 poin, 261 komentar; konteks personal AI |
| [item 46760589](https://news.ycombinator.com/item?id=46760589) | Jan 2026 | Contoh positif: penghematan beberapa jam |
| [item 46761513](https://news.ycombinator.com/item?id=46761513) | Jan 2026 | Contoh positif: ringkasan jadwal keluarga |
| [item 46760586](https://news.ycombinator.com/item?id=46760586) | Jan 2026 | Keluhan setup yang merepotkan |

### Forum & referensi desain

| Sumber | Dipakai untuk |
|---|---|
| [Obsidian forum 71832](https://forum.obsidian.md/t/how-do-you-measure-whether-a-system-is-good/71832) | Beban memelihara sistem; kelelahan mengambil keputusan |
| [Obsidian forum 36106](https://forum.obsidian.md/t/a-maintainable-second-braind-for-someone-with-adhd/36106) | Waktu pengaturan plugin dinilai terlalu besar |
| [Graphiti](https://github.com/getzep/graphiti) | Pembanding: fakta dengan masa berlaku + provenance |
| [NVIDIA — Memory-Driven Chief of Staff](https://developer.nvidia.com/blog/building-a-memory-driven-agent-with-nvidia-nemoclaw/) | Pembanding: self model + ledger + koreksi |

### Issue pendukung tambahan (ditemukan dalam penelusuran, di luar ringkasan awal)

- [#3841](https://github.com/mem0ai/mem0/issues/3841) (Mem0) — ketidakkonsistenan UI vs penyimpanan;
  ditutup karena komponen OpenMemory dihentikan, bukan karena diperbaiki.
- [#35186](https://github.com/NousResearch/hermes-agent/issues/35186) (Hermes) — penghapusan
  entri memori permanen; ditutup "out of scope" oleh maintainer.
- [#31054](https://forum.obsidian.md/t/create-dataview-table-of-multiple-tasks-within-notes/31054)
  (Forum Obsidian) — contoh tugas yang tersebar di banyak catatan.

## 8. Keterbatasan & langkah validasi berikutnya

**Keterbatasan:**

1. Bukti bersifat kualitatif; laporan publik lebih mewakili orang yang mengalami masalah.
2. Status issue dapat berubah setelah tanggal pemeriksaan.
3. Kutipan mencerminkan pengalaman masing-masing pelapor, bukan rata-rata pengguna.
4. Sintesis sebab–akibat adalah interpretasi kita dan belum diuji.

**Langkah validasi:**

1. Susun 3–5 skenario uji berdasarkan laporan di atas (contoh: fakta berubah, kegagalan kirim,
   klaim selesai tanpa bukti).
2. Jalankan skenario terhadap minimal dua pendekatan pembanding sebelum membangun penuh.
3. Wawancarai 3–5 pengguna personal AI yang pernah mendelegasikan pekerjaan nyata.
4. Tetapkan ambang keberhasilan dan ukur kondisi awal sebelum evaluasi.
5. Perbarui dokumen ini dengan hasilnya; jangan mengubah klaim tanpa bukti baru.