# Skenario Validasi W1 — Menguji Rumusan Masalah v1.0

- **Versi:** 1.0 — 2 Oktober 2026
- **Menguji:** [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) v1.0 — kondisi F1, sekaligus menetapkan baseline M1–M5
- **Prinsip penting:** **belum ada Mitra.** Yang diukur adalah cara kerja saat ini. Skenario yang sama
  akan dijalankan ulang terhadap Mitra di W3–W4 — inilah desain pre/post.

## Cara memakai dokumen ini

1. Jalankan S1–S5 dengan alat yang sekarang benar-benar dipakai (OpenCode/chat AI, bot pribadi,
   pengingat apa pun). Jangan mengubah perilaku normal demi skenario.
2. Setiap intervensi manual dicatat di `validation/observation_log.csv` (salin dari template;
   file kerja berisi data asli ini di-gitignore).
3. S1, S3, S5 bisa mulai hari ini. S2 dan S4 butuh kanal + penjadwal; jika belum ada, catat
   "belum tersedia" — itu sendiri temuan — dan jalankan versi manualnya.
4. Koreksi hanya bila memang akan kamu lakukan sehari-hari. Jangan "membantu" asisten secara
   artifisial — kita ingin mengukur perilaku alaminya.
5. Akhir W1: hitung baseline, isi gate keputusan, perbarui PROBLEM_STATEMENT bila perlu
   (versi baru + catatan bukti).

**Etika & privasi (wawancara):** minta izin partisipan; kutipan dicatat tanpa data pribadi;
data mentah tidak masuk repo publik — hanya ringkasan anonim.

## Ringkasan skenario

| ID | Nama | Beban yang diuji | Sumber komunitas | Metrik | Durasi | Bisa solo? |
|---|---|---|---|---|---|---|
| S1 | Instruksi berubah di tengah jalan | Konteks | mem0 #4956, claude-code #85677 | M1, M2 | 2–3 hari | Ya |
| S2 | Tugas terjadwal tanpa pengawasan | Eksekusi | hermes #112712, openclaw #8298 | M1, M4 | 3–4 hari | Butuh penjadwal |
| S3 | Klaim "selesai" tanpa bukti | Hasil | openclaw #44925, gemini-cli #22323 | M3, M1 | 1 hari | Ya |
| S4 | Kegagalan pengiriman yang senyap | Hasil | hermes #112712, openclaw #44925 | M4 | 1–2 hari | Butuh kanal |
| S5 | Beban pemeliharaan & koreksi berulang | Semua | forum Obsidian, claude-code #8209 | M1, M5 | 1 minggu (paralel) | Ya |

## S1 — Instruksi berubah di tengah jalan

**Yang diuji:** ketika instruksi berubah, apakah asisten memakai versi terbaru tanpa kamu harus
mengulanginya?

**Sumber:** Mem0 #4956 (fakta lama menang atas fakta baru); Claude Code #85677 (dua catatan
memori bertabrakan, yang salah menang).

**Persiapan:** pilih 1 komitmen nyata yang melibatkan AI — misalnya ringkasan mingguan, rencana
belajar, atau draft dokumen.

**Langkah:**

1. Hari 1: nyatakan instruksi awal secara lengkap (lingkup, format, tenggat) dalam satu sesi.
2. Hari 2: di sesi/percakapan **baru**, ubah satu parameter saja (mis. tenggat dimajukan,
   cakupan dipersempit). Jangan mengulang parameter lain.
3. Hari 3: minta asisten melanjutkan atau mengerjakan komitmen itu.

**Yang diamati dan dicatat:**

- Apakah versi lama muncul (tenggat/cakupan lama)?
- Berapa koreksi yang diperlukan sebelum benar?
- Apakah kamu harus mengulang konteks dari awal?

**Ukuran:** M1 (jumlah intervensi), M2 (insiden instruksi kedaluwarsa dipakai).

**Sinyal falsifikasi:** instruksi terbaru selalu dipakai; nol koreksi; nol pengulangan konteks —
pada 2–3 hari pengujian.

## S2 — Tugas terjadwal tanpa pengawasan

**Yang diuji:** apakah kamu tahu tugas terjadwal benar-benar berjalan dan hasilnya sampai —
tanpa harus memeriksa?

**Sumber:** Hermes #112712 (tugas sukses tapi gagal kirim, tanpa pemberitahuan); OpenClaw #8298
(reminder gagal senyap).

**Prasyarat:** ada cara menjadwalkan tugas berulang ke kanal yang kamu pakai (bot Telegram
pribadi, cron + AI, atau asisten komersial). Jika belum ada: catat "belum tersedia" dan
lanjutkan versi manual (kamu yang mengeksekusi, pengingat kalender biasa).

**Langkah:**

1. Jadwalkan 1 tugas berulang sederhana selama 3–4 hari (mis. ringkasan singkat tiap pagi ke
   kanal pilihan).
2. Setelah dijadwalkan, **jangan** memeriksa daftar tugas secara proaktif.
3. Catat setiap kali kamu *merasa perlu* memeriksa ("just in case") — ini tetap dihitung
   sebagai beban pengawasan.

**Yang diamati dan dicatat:**

- Tugas berjalan? Hasil datang lengkap? Ada kegagalan — dan kapan kamu sadar, bagaimana?
- Berapa kali kamu terdorong memeriksa manual.

**Ukuran:** M4 (waktu deteksi kegagalan), M1 (pemeriksaan manual, termasuk "just in case").

**Sinyal falsifikasi:** semua tugas berjalan; hasil selalu lengkap; kamu tidak pernah merasa
perlu memeriksa; kegagalan (jika ada) langsung diberitahukan.

## S3 — Klaim "selesai" tanpa bukti

**Yang diuji:** ketika AI bilang "selesai", apakah kamu langsung percaya — atau harus
memverifikasi?

**Sumber:** OpenClaw #44925 (klaim berkas dibuat padahal tidak ada); Gemini CLI #22323 (batas
giliran dilaporkan sebagai sukses).

**Persiapan:** pilih tugas yang menghasilkan artefak yang bisa diperiksa: file, catatan, pesan
terkirim, daftar tautan.

**Langkah:**

1. Delegasikan tugas itu ke AI yang biasa dipakai dan minta laporan singkat.
2. Saat AI menyatakan selesai, verifikasi artefaknya.
3. Catat: benar/salah klaimnya, dan berapa langkah + menit untuk verifikasi.

**Yang diamati:** klaim palsu/berlebihan; usaha verifikasi; apakah status "selesai" dibedakan
dari "hasil tersedia".

**Ukuran:** M3 (klaim tanpa bukti ÷ total klaim), M1 (langkah verifikasi).

**Sinyal falsifikasi:** semua klaim tervalidasi cepat (≤1 langkah), tanpa insiden klaim palsu.

## S4 — Kegagalan pengiriman yang senyap

**Yang diuji:** apakah kegagalan kirim terlihat di jalur yang benar — atau hanya tercatat di
suatu tempat yang tidak dibaca?

**Sumber:** Hermes #112712 (topik Telegram dihapus → kirim gagal, operator tidak diberi tahu);
OpenClaw #44925 (announce gagal → hasil hilang).

**Prasyarat:** kanal pengiriman (Telegram/WhatsApp/dll). Jangan sengaja merusak kanal produksi —
gunakan kanal uji kecil yang boleh dirusak (mis. bot uji + grup uji yang lalu diarsipkan/di-mute),
atau tunggu kegagalan nyata terjadi.

**Langkah:**

1. Gunakan kanal uji untuk 1–2 tugas terjadwal.
2. Pada titik tertentu, putuskan jalur pengiriman (arsipkan grup / mute / keluarkan bot) —
   atau tunggu kegagalan nyata.
3. Amati bagaimana dan kapan kamu diberi tahu.

**Yang diamati:** apakah kegagalan kirim dibedakan dari kegagalan proses; apakah ada
pemberitahuan ke jalur alternatif; waktu sampai kamu sadar.

**Ukuran:** M4.

**Sinyal falsifikasi:** kegagalan kirim muncul sendiri di jalur alternatif dalam hitungan menit,
dengan label tahap yang benar.

## S5 — Beban pemeliharaan & koreksi berulang (paralel 1 minggu)

**Yang diuji:** berapa waktu untuk mengurus asisten + berapa sering mengoreksi hal yang sama.

**Sumber:** forum Obsidian (kelelahan mengatur sistem); Claude Code #8209 (pola kerja prosedural
dilupakan dan diajari berulang).

**Langkah (sepanjang minggu):**

1. Catat setiap menit untuk konfigurasi, memperbaiki plugin, mengatur ulang.
2. Catat setiap koreksi terhadap hal yang **sudah pernah** dikoreksi sebelumnya.

**Ukuran:** M1 (koreksi berulang), M5 (komponen biaya: menit pemeliharaan + menit koreksi).

**Sinyal falsifikasi:** nyaris nol pemeliharaan; tidak ada koreksi berulang.

## Cara menghitung baseline (akhir W1)

Rumus:

- **M1** = jumlah intervensi (kategori di bawah) ÷ jumlah tugas yang didelegasikan dalam jendela
  pengukuran.
- **M2** = jumlah insiden instruksi kedaluwarsa (S1).
- **M3** = klaim selesai yang gagal verifikasi ÷ total klaim (S3).
- **M4** = median selisih waktu antara kegagalan sebenarnya (dari bukti log/sistem) dan saat
  kamu menyadarinya (S2/S4). Bila tidak ada kegagalan: tandai "tidak ada insiden" — **jangan**
  catat 0 seolah lulus; pertimbangkan memperpanjang jendela.
- **M5** = estimasi waktu dihemat − (menit pemeliharaan + menit koreksi) selama 1 minggu.

Kategori intervensi untuk log:

| Kode | Arti |
|---|---|
| `context_restated` | mengulang konteks/instruksi |
| `status_checked_manually` | memeriksa status tanpa diminta sistem |
| `re_asked` | menanyakan ulang hal yang sama |
| `corrected_wrong_info` | mengoreksi info yang salah/kedaluwarsa |
| `re_verified_claim` | memverifikasi ulang klaim "selesai" |
| `setup_repaired` | memperbaiki konfigurasi/plugin |
| `other` | jelaskan di kolom deskripsi |

## Wawancara partisipan (3–5 orang) — untuk F2/A1

**Kriteria:** pernah/sedang memakai personal AI untuk pekerjaan berulang nyata (bot Telegram
pribadi, ChatGPT/Claude dengan memori, agen self-hosted).

**Pertanyaan (berbasis kejadian terakhir, bukan opini umum):**

1. Tugas apa yang terakhir kamu delegasikan secara rutin ke AI-mu?
2. Bagaimana kamu biasanya tahu hasilnya sudah sampai dan benar?
3. Ceritakan kejadian terakhir saat AI memakai info/pedoman lama yang sudah kamu ubah.
4. Saat tugas terjadwal gagal, bagaimana dan kapan kamu tahu?
5. Berapa kali seminggu kamu mengoreksi AI untuk hal yang itu-itu lagi?
6. Ketika AI bilang "selesai", bagaimana kamu memverifikasi — dan berapa lama?
7. Berapa waktu seminggu untuk mengurus/merawat asisten itu?
8. Kalau besok ada asisten yang bisa dipercaya soal ini, bagian mana yang paling kamu inginkan?

**Ambang "mengenali pola":** partisipan melaporkan ≥2 dari 3 beban **dengan contoh kejadian
nyata**.

## Gate keputusan (akhir W1)

| Hasil | Tindakan |
|---|---|
| ≥2 dari 3 beban terkonfirmasi pada diri sendiri (S1–S5) **dan** ≥2/5 partisipan mengenali pola | Lanjut: masalah tetap terkunci v1.0; baseline tercatat; selaraskan arsitektur |
| Hanya 1 beban terkonfirmasi | Sempitkan rumusan ke beban itu (naikkan ke v1.1) |
| 0 beban (F2) | Asumsi A1 gugur → kembali ke kandidat lain di COMMUNITY_RESEARCH.md |
| Pembanding sederhana (catatan + pengingat) sudah menyelesaikan M1–M4 (F3) | Ubah pembeda sebelum membangun |
| Manfaat bersih ≤ 0 (F4) | Sederhanakan mekanisme, bukan menambah fitur |

## Jadwal W1 (2–9 Okt)

| Hari | Aktivitas |
|---|---|
| 1 (2–3 Okt) | Siapkan log; jalankan S3 (1 hari); mulai S1 langkah 1; klaim kredit + API key |
| 2 | S1 langkah 2; setup S2/S4 jika kanal tersedia |
| 3–5 | Observasi S2/S4; S5 berjalan; smoke test Token Factory |
| 6–7 (8–9 Okt) | Wawancara; hitung baseline; isi gate keputusan; perbarui dokumen |

## Keluaran W1

1. `validation/observation_log.csv` terisi (lokal; tidak di-commit).
2. Ringkasan baseline (M1–M5) + hasil wawancara anonim → ditambahkan ke dokumen ini sebagai
   bagian **"Hasil"**.
3. Keputusan gate: lanjut / sempitkan / ubah — beserta catatan bukti.