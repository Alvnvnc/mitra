# Rumusan Masalah Mitra — Terkunci

- **Versi:** 1.0 (terkunci)
- **Tanggal:** 2 Oktober 2026
- **Status:** terkunci — perubahan hanya melalui bukti baru (lihat bagian 8)
- **Bukti pendukung:** [COMMUNITY_RESEARCH.md](COMMUNITY_RESEARCH.md)
- **Dokumen terkait:** [PLAN.md](PLAN.md), [ARCHITECTURE.md](ARCHITECTURE.md)

## Ringkasan (English — untuk referensi)

> **Problem:** Users of a personal AI who delegate recurring commitments through conversation
> still carry the oversight burden: they must keep instructions current themselves, verify that
> tasks actually ran, and chase results or failures. This erodes the net benefit of delegation
> and lowers trust.
>
> **Objectives (v1):** (O1) only current, user-approved instructions are used; (O2) "done" claims
> require verified result evidence; (O3) failures surface without the user asking; (O4) net
> maintenance cost is lower than time saved; (O5) everything runs on open infrastructure —
> NVIDIA Nemotron via Nebius Token Factory.

*(Versi Indonesia di bawah adalah rujukan utama; terjemahan Inggris akan disempurnakan
menjelang submission.)*

## 1. Pernyataan masalah (terkunci)

> **Pengguna personal AI yang mendelegasikan komitmen berulang melalui percakapan tetap
> menanggung beban pengawasan: mereka harus menjaga sendiri agar instruksi terbaru dipakai,
> memastikan tugas benar-benar berjalan, dan memverifikasi hasil serta kegagalannya. Beban ini
> mengurangi manfaat delegasi dan menurunkan kepercayaan.**

Tiga beban yang harus hilang — masing-masing terukur:

1. **Konteks** — instruksi yang dipakai harus versi terbaru yang disetujui pengguna.
2. **Eksekusi** — status tugas harus terikat bukti, bukan klaim proses.
3. **Hasil** — keberhasilan dan kegagalan harus terlihat tanpa dicari.

## 2. Pengguna target

- **Primer:** satu orang (solo builder / knowledge worker) yang **sudah** memakai personal AI
  untuk pekerjaan nyata berulang: riset, ringkasan, pengingat, tindak lanjut — dan
  menjalankannya sendiri (self-hosted atau akun pribadi).
- **Bukan target v1:** tim/enterprise, agen fisik (robotics), pengguna chat sesekali tanpa
  delegasi nyata.

## 3. Situasi sasaran

1. Instruksi berubah antar waktu/sesi (contoh: cakupan dan tanggal pengiriman diubah sehari
   sebelum jatuh tempo).
2. Tugas berjalan tanpa pengawasan (terjadwal/background) dan hasilnya harus sampai ke pengguna.
3. Kegagalan dapat terjadi di tahap berbeda (proses, penyimpanan, pengiriman) dan harus terlihat
   pada tahap yang benar.
4. Pengguna mengoreksi setelah kejadian; koreksi harus bertahan lintas sesi.

## 4. Ruang lingkup (v1)

**Termasuk:**

- Personal AI single-user dengan percakapan sebagai antarmuka utama (Telegram + web).
- Komitmen berulang: jadwal, ringkasan, riset tersimpan, tindak lanjut.
- Kebenaran konteks: versi instruksi aktif + riwayat perubahan + sumber.
- Verifikasi hasil: klaim selesai wajib punya bukti yang diperiksa; pengiriman punya status
  terpisah dari hasil.
- Visibilitas kegagalan: pemberitahuan tanpa pengguna harus bertanya.
- Biaya pemeliharaan dihitung sebagai bagian dari manfaat bersih.

**Tidak termasuk (v1):**

- Multi-user/enterprise, RBAC, audit organisasi.
- Tindakan berisiko tinggi tanpa persetujuan manusia (pembayaran, komunikasi eksternal tanpa
  review).
- Menjanjikan model bebas halusinasi; fokus pada kebenaran konteks dan pelacakan hasil.
- Robotics / physical AI.

## 5. Asumsi yang harus diuji

- **A1:** Pengguna yang sudah memakai personal AI mengalami minimal dua dari tiga beban
  (konteks, eksekusi, hasil) secara rutin.
- **A2:** Beban pengawasan cukup besar sehingga terasa mengurangi manfaat delegasi.
- **A3:** Pengguna lebih memilih pemeriksaan ringan yang andal daripada fitur baru yang menambah
  pemeliharaan.
- **A4:** Masalah ini bisa dikurangi secara terukur dengan mekanisme "komitmen + bukti + status"
  tanpa memerlukan model yang jauh lebih besar.

## 6. Tujuan solusi (objectives)

- **O1:** Hanya instruksi terbaru yang disetujui pengguna yang dipakai — dapat ditelusuri.
- **O2:** Klaim "selesai" hanya muncul dengan bukti hasil yang diperiksa.
- **O3:** Kegagalan proses/pengiriman terlihat oleh pengguna tanpa diminta.
- **O4:** Manfaat bersih bernilai positif: waktu dihemat > (pemeliharaan + koreksi).
- **O5:** Berjalan di infrastruktur terbuka — NVIDIA Nemotron via Nebius Token Factory.

## 7. Metrik keberhasilan

| # | Metrik | Kondisi asal | Target |
|---|---|---|---|
| M1 | Intervensi manual per tugas (koreksi konteks + cek status ÷ jumlah tugas) | cara lama pengguna (diukur di W1) | turun ≥50% terhadap baseline |
| M2 | Insiden menggunakan instruksi kedaluwarsa | ada | 0 pada skenario uji |
| M3 | Klaim "selesai" tanpa bukti hasil | ada | 0 pada skenario uji |
| M4 | Waktu sampai pengguna tahu suatu kegagalan | "saat kebetulan bertanya" | tanpa bertanya; ≤1 jam pada skenario uji |
| M5 | Manfaat bersih = waktu dihemat − (pemeliharaan + koreksi) | — | > 0 pada uji |

Ambang final ditetapkan setelah baseline W1 diukur. Angka di atas adalah target awal yang boleh
diperketat — bukan dilunakkan tanpa catatan.

## 8. Kapan rumusan ini direvisi

Rumusan ini terkunci, tetapi **bukan dogma**. Revisi hanya terjadi dengan bukti baru:

- **F1:** Jika pada uji skenario awal, pengguna (termasuk pembangun sendiri) tidak mengalami
  minimal dua dari tiga beban → rumusan disempitkan atau target diubah.
- **F2:** Jika <2 dari 5 wawancara mengenali pola ini → asumsi A1 gugur; kembali ke kandidat
  lain di COMMUNITY_RESEARCH.md.
- **F3:** Jika pembanding sederhana (catatan terstruktur + pengingat) mencapai M1–M4 → pembeda
  harus diubah.
- **F4:** Jika manfaat bersih ≤ 0 → mekanisme disederhanakan, bukan ditambah fitur.

Setiap revisi: naikkan versi, catat buktinya, dan perbarui PLAN serta COMMUNITY_RESEARCH bila
perlu.

## 9. Keterkaitan dokumen

- Bukti masalah: [COMMUNITY_RESEARCH.md](COMMUNITY_RESEARCH.md) — 13 issue GitHub + Hacker News
  + forum, diperiksa 2 Oktober 2026.
- Rencana eksekusi: [PLAN.md](PLAN.md).
- Arsitektur: [ARCHITECTURE.md](ARCHITECTURE.md) — akan diselaraskan setelah validasi skenario W1.

## Riwayat revisi

| Versi | Tanggal | Perubahan | Dasar |
|---|---|---|---|
| 1.0 | 2026-10-02 | Rumusan terkunci (dari kandidat riset komunitas) | COMMUNITY_RESEARCH.md |