# Nebius Serverless Jobs — Catatan Operasional

- **Tanggal riset/akses:** 2026-10-02
- **Konteks:** evaluasi opsi W3 untuk Mitra — menjalankan konsolidasi memori malam sebagai Nebius Serverless Job vs tetap cron di VM.
- **Metode:** pembacaan langsung dokumentasi resmi `docs.nebius.com` (halaman `.md`), CLI reference, REST reference, halaman harga/kuota Compute, dan README SDK resmi. Semua klaim faktual di catatan ini memiliki tautan sumber; klaim yang tidak dapat diverifikasi ditandai `[BELUM TERVERIFIKASI]`. Bagian "Implikasi untuk Mitra" adalah analisis turunan dari fakta yang dikutip dan ditandai sebagai inferensi.

---

## 1. Ringkasan

Serverless AI Jobs adalah layanan Nebius untuk menjalankan container image sebagai workload batch non-interaktif (one-off); setiap job berjalan di container VM Compute yang dikelola layanan dan dihapus otomatis setelah selesai/gagal ([manage](https://docs.nebius.com/serverless/jobs/manage), [overview](https://docs.nebius.com/serverless/overview)). Submission dapat dilakukan lewat web console, CLI (`nebius ai job create`), REST API (`POST https://api.nebius.cloud/ai/v1/jobs`), dan SDK ([manage](https://docs.nebius.com/serverless/jobs/manage), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create), [pysdk README](https://github.com/nebius/pysdk)). Timeout job dapat diatur dengan batas minimum 1 jam, maksimum 168 jam, default 24 jam ([CLI create](https://docs.nebius.com/cli/reference/ai/job/create)). Retry otomatis hanya tersedia lewat `--restart-policy on-failure` dan hanya bereaksi terhadap exit code container; kegagalan kapasitas, preemption, VM berhenti, dan startup failure tidak di-retry otomatis ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts)). Tidak ditemukan mekanisme penjadwalan bawaan (cron/scheduler) yang terdokumentasi untuk Jobs — kata "scheduled" hanya muncul sebagai frasa deskriptif, bukan fitur ([manage](https://docs.nebius.com/serverless/jobs/manage), [indeks docs](https://docs.nebius.com/llms.txt), [CLI job](https://docs.nebius.com/cli/reference/ai/job)). Harga dan kuota Serverless AI mengikuti Compute (per detik, hanya saat berjalan); contoh tarif terdokumentasi per 2026-10-01: CPU AMD EPYC Genoa \$0.015/vCPU-jam, RAM \$0.0045/GiB-jam ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [Compute pricing](https://docs.nebius.com/compute/resources/pricing)). Terdapat inkonsistensi dokumentasi soal ketersediaan region: halaman indeks Serverless menyebut "all public regions", sementara matriks region resmi menunjukkan tidak tersedia di `eu-south1`, `us-north1`, dan `eu-north2` ([serverless index](https://docs.nebius.com/serverless/index), [regions](https://docs.nebius.com/overview/regions)).

---

## 2. Cara Kerja Serverless Jobs

### 2.1 Model eksekusi

- Job menjalankan **container image** sebagai batch workload non-interaktif: "Serverless AI jobs run container images as one-off or scheduled batch workloads", cocok untuk training, fine-tuning, dan data processing ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Setiap job berjalan di **container VM Compute** yang dikelola Serverless AI dan **ditagih hanya saat job berjalan** ([manage](https://docs.nebius.com/serverless/jobs/manage), [pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)).
- Job **tidak mendukung stop/start**; ia berjalan sampai workload selesai, timeout, atau dibatalkan ([overview](https://docs.nebius.com/serverless/overview), [manage](https://docs.nebius.com/serverless/jobs/manage)).
- Saat job selesai sukses atau gagal, **container VM dihapus otomatis**; volume yang di-mount tetap ada dan harus dihapus manual ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Status job yang terdokumentasi: `PROVISIONING → STARTING → IMAGE_PULLING → RUNNING → COMPLETED`, dengan `CANCELLING/CANCELLED`, `FAILED`, `ERROR`, `DELETING` sebagai kemungkinan lain. `FAILED` = masalah di workload (kode/image/timeout), `ERROR` = masalah internal atau kapasitas ([lifecycle](https://docs.nebius.com/serverless/lifecycle)).
- Pembuatan job "usually takes a few minutes" (termasuk pull image) ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Jika kapasitas platform/preset yang diminta tidak tersedia saat start, Serverless AI mencoba hingga **30 menit**, lalu job masuk `ERROR` dengan kode `NotEnoughResources` dan **tidak di-retry otomatis** ([lifecycle](https://docs.nebius.com/serverless/lifecycle)).

### 2.2 Cara submit (CLI / SDK / console / REST)

- **Web console:** Serverless AI → Jobs → Create job (form lengkap: image, registry, env & secret env, timeout, resource GPU/CPU, disk, volume, inject file, SSH, subnet/IP) ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- **CLI — deterministik (cocok untuk skrip/CI/agen):**
  ```bash
  nebius ai job create \
    --name <job_name> --image <image_path> \
    --container-command "<command>" --args "<arguments>" \
    --env <key=value> --env-secret <key=secret_selector> \
    --timeout <duration> --platform <platform_ID> --preset <preset> \
    --disk-size <size> --volume <source:container_path[:mode]> \
    --subnet-id <subnet_ID> --restart-policy <never|on-failure>
  ```
  Tersedia juga wizard interaktif `nebius ai create --type job` ([manage](https://docs.nebius.com/serverless/jobs/manage), [CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).
- **CLI — perintah lain:** `nebius ai job list`, `get`, `get-by-name`, `logs`, `cancel`, `delete`, `restart`, `ssh`, dan `nebius ai job run` (menjalankan skrip Python lokal sebagai one-off Job, status **BETA**) ([CLI job](https://docs.nebius.com/cli/reference/ai/job)).
- **REST API:** `POST https://api.nebius.cloud/ai/v1/jobs` dengan Bearer access token; contoh body tercantum di dokumentasi. Log job **tidak** tersedia lewat REST — hanya console dan CLI ([manage](https://docs.nebius.com/serverless/jobs/manage), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).
- **SDK:** Nebius menyediakan SDK Go, Python, dan TypeScript; README Python SDK menyatakan SDK "supports all APIs in the Nebius API repository" (JobService termasuk API tersebut, lihat REST reference). Namun README yang diperiksa **tidak memuat contoh khusus pembuatan job** ([pysdk README](https://github.com/nebius/pysdk), [SDK list di llms.txt](https://docs.nebius.com/llms.txt), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).
- Autentikasi REST memakai access token, misalnya dari `nebius iam get-access-token`; halaman REST reference job memakai format `Authorization: Bearer <access_token>` ([manage](https://docs.nebius.com/serverless/jobs/manage), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).

### 2.3 Penjadwalan

- Dokumentasi mendeskripsikan job sebagai "one-off **or scheduled** batch workloads", tetapi **tidak menjelaskan mekanisme penjadwalan apa pun** ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- **Tidak ditemukan** di [indeks dokumentasi](https://docs.nebius.com/llms.txt) halaman khusus penjadwalan jobs; daftar subperintah [CLI `nebius ai job`](https://docs.nebius.com/cli/reference/ai/job) juga tidak memuat perintah `schedule`/`cron`.
- Pencarian teks pada korpus dokumentasi Serverless/Compute (via MCP dokumen Nebius, 2026-10-02) tidak menemukan istilah "cron" ([docs MCP](https://docs.nebius.com/mcp), [llms.txt](https://docs.nebius.com/llms.txt)).
- **Kesimpulan operasional:** tidak ada bukti bahwa penjadwalan berulang adalah fitur bawaan Serverless AI. Untuk job malam berulang, trigger eksternal tetap dibutuhkan (mis. cron/systemd timer di VM, CI, atau scheduler eksternal yang memanggil CLI/REST). `[BELUM TERVERIFIKASI: apakah tersedia fitur penjadwalan di luar dokumentasi publik / perlu konfirmasi support Nebius]`

### 2.4 Timeout

- `--timeout` (CLI) / `spec.timeout` (REST): **minimum 1 jam (`3600s`), maksimum 168 jam (`604800s`), default 24 jam (`86400s`)** ([manage](https://docs.nebius.com/serverless/jobs/manage), [CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).
- Timeout adalah durasi "setelah job dibatalkan jika belum selesai"; job yang melewati timeout berakhir `FAILED` dengan kode `TimeoutExceeded` ([quickstart jobs](https://docs.nebius.com/serverless/quickstart/jobs), [lifecycle](https://docs.nebius.com/serverless/lifecycle)).
- Job juga bisa dihentikan manual: `nebius ai job cancel <job_ID>` atau REST `POST /ai/v1/jobs/cancel`; cancel langsung mematikan VM dan menghapus container disk ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Catatan: karena timeout minimum 1 jam, job yang menggantung **tidak bisa** dimatikan otomatis oleh timeout lebih cepat dari 1 jam ([CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).

### 2.5 Retry / automatic restarts

- Default `--restart-policy never`: job berjalan sekali; jika container exit dengan error, job `FAILED` dan tidak di-restart ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts), [CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).
- `--restart-policy on-failure`: Serverless AI me-restart container jika exit code non-zero; berguna untuk kegagalan transien yang bisa lanjut dari checkpoint. Field REST terkait: `spec.restartAttempts` ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).
- Restart otomatis **tidak menangani**: kapasitas tidak tersedia saat start, preemption (VM preemptible), VM berhenti tak terduga, serta startup failure/timeout. Untuk kasus ini job masuk `ERROR` dan harus dijalankan ulang manual (`nebius ai job restart` atau buat job baru) ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts), [CLI job](https://docs.nebius.com/cli/reference/ai/job)).
- Preemptible VM (lebih murah) **hanya tersedia untuk platform GPU**; VM tanpa GPU hanya tipe regular ([manage](https://docs.nebius.com/serverless/jobs/manage), [preemptible](https://docs.nebius.com/compute/virtual-machines/preemptible)).

### 2.6 Log, metrik, dan volume

- Log job hanya dapat dilihat di web console dan CLI (`nebius ai job logs <job_ID> --follow|--since|--tail|--until|--timestamps`) — tidak tersedia via REST ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Metrik job muncul di tab **Metrics** console; data tersedia **5–10 menit setelah resource dibuat**, refresh default tiap 15 detik; VM dasar tidak muncul di Compute ([monitoring](https://docs.nebius.com/serverless/monitoring)).
- Volume (bucket Object Storage atau shared filesystem) dapat di-mount ke job; volume bertahan dan harus dihapus manual setelah job selesai. Env sensitif dapat diambil dari SecretStash via `--env-secret`/`--registry-secret` ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Untuk debug kegagalan, pola resmi "sleep-on-fail" (`--container-command bash --args "-lc '<cmd> || (echo FAILED; sleep 86400)'"`) menjaga VM tetap hidup 24 jam agar bisa di-SSH; tanpa itu VM langsung dihapus ([failure](https://docs.nebius.com/serverless/jobs/failure)).

---

## 3. Kapasitas & Harga

### 3.1 Prinsip penagihan (terdokumentasi)

- **Serverless AI tidak punya harga/kuota sendiri**; layanan memakai harga dan kuota **Compute**. Deployment (job/endpoint/Devlab) dihitung terhadap kuota Compute ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)).
- Saat job berjalan, tagihan mengikuti **Compute VM dan disk**: billing unit **1 detik**, pricing unit **1 jam** (biaya dihitung proporsional) ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [Compute pricing](https://docs.nebius.com/compute/resources/pricing)).
- Job **tidak bisa di-stop** — hanya berjalan, selesai, timeout, cancel, atau delete ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [manage](https://docs.nebius.com/serverless/jobs/manage)).
- Bucket/shared filesystem yang di-mount ditagih terpisah sesuai harga Object Storage / shared filesystem, termasuk saat deployment berhenti ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)).

### 3.2 Tarif terdokumentasi (USD, tanpa pajak; berlaku dari 2026-10-01)

Diambil dari [Compute pricing](https://docs.nebius.com/compute/resources/pricing):

| Item | Tarif | Satuan |
| - | - | - |
| Non-GPU AMD EPYC Genoa — CPU | \$0.015 | 1 CPU-jam |
| Non-GPU AMD EPYC Genoa — RAM | \$0.0045 | 1 GiB-jam |
| NVIDIA H200 NVLink | \$5.40 | 1 GPU-jam |
| Preemptible H200 | \$2.45 | 1 GPU-jam |
| NVIDIA H100 NVLink (hanya `eu-north1`) | \$4.50 | 1 GPU-jam |
| Preemptible H100 | \$2.15 | 1 GPU-jam |
| NVIDIA L40S (Intel/AMD, hanya `eu-north1`) | \$1.35 | 1 GPU-jam |
| Preemptible L40S | \$0.65 | 1 GPU-jam |
| Network SSD disk | \$0.071 | 1 GiB per 730 jam |

**Contoh turunan (bukan angka dokumentasi — hasil hitung dari tarif di atas):** presets `8vcpu-32gb` (cpu-d3) ≈ 8 × \$0.015 + 32 × \$0.0045 = **\$0.264/jam berjalan**; ditambah container disk default 250 GiB Network SSD ≈ 250 × \$0.071 / 730 ≈ **\$0.024/jam** → total ≈ **\$0.29 per jam berjalan** (tanpa volume/bucket). Tipe disk default container tidak disebut eksplisit di dokumentasi (contoh REST memakai `NETWORK_SSD`) `[BELUM TERVERIFIKASI]` ([Compute pricing](https://docs.nebius.com/compute/resources/pricing), [manage](https://docs.nebius.com/serverless/jobs/manage), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).

### 3.3 Kuota terdokumentasi (contoh yang relevan)

Dari [Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits) (default per region, dapat dinaikkan lewat permintaan kuota):

- VM GPU regular: **12** per region (semua region publik); preemptible: **8**.
- Total GPU tanpa reservasi (contoh): H200 **32** di `eu-north1`, **8** di `eu-west1`, **0** di `us-central1`; H100 **32** di `eu-north1`; L40S **2** di `eu-north1`; RTX PRO 6000 **32** di `uk-south2`; B300 **32** di `uk-south1`/`eu-west2`; B200 **0** di `me-west1`/`us-central1`.
- Non-GPU: **12 VM** dan **total 200 vCPU** per region publik.
- Storage: total kapasitas disk Network SSD **2–5 TiB** tergantung region.
- Kuota berlaku selama siklus hidup VM (creation → deletion); job yang sedang berjalan memakai slot VM/GPU ([Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits), [pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)).

### 3.4 Kapasitas runtime

- Jika kapasitas tidak tersedia saat start, layanan mencoba hingga **30 menit** (regular maupun preemptible), lalu `ERROR`/`NotEnoughResources`; tidak ada retry otomatis ([lifecycle](https://docs.nebius.com/serverless/lifecycle)).
- **Tidak ditemukan** angka kapasitas fisik atau throughput job per region di dokumentasi publik `[BELUM TERVERIFIKASI]` (Capacity advisor yang terdokumentasi hanya untuk VM GPU: [capacity advisor](https://docs.nebius.com/compute/virtual-machines/capacity-advisor)).
- **Tidak ditemukan** batas jumlah job konkuren khusus Serverless (di luar kuota Compute di atas) `[BELUM TERVERIFIKASI]` ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits)).

---

## 4. Region & Dukungan GPU

### 4.1 Ketersediaan Serverless AI per region

Matriks resmi [regions](https://docs.nebius.com/overview/regions) menunjukkan Serverless AI tersedia di:

`eu-north1` (Finlandia), `eu-west1` (Prancis), `eu-west2` (Prancis), `me-west1` (Israel), `us-central1` (Kansas City), `uk-south1`, `uk-south2` (UK).

Tidak tersedia (tanda "—"): `eu-south1` (Madrid), `us-north1` (Minnesota), dan `eu-north2` (Iceland, region privat).

**Pertentangan dokumentasi:** halaman [serverless index](https://docs.nebius.com/serverless/index) menyatakan layanan "available in all public Nebius AI Cloud regions", padahal matriks di [regions](https://docs.nebius.com/overview/regions) tidak mencentang `eu-south1` dan `us-north1`. Dicatat apa adanya; sumber otoritatif untuk pemilihan region sebaiknya dikonfirmasi via console/kuota proyek `[BELUM TERVERIFIKASI: region mana yang benar]`.

### 4.2 GPU yang relevan di region Serverless

Job memakai platform/preset Compute ([quickstart jobs](https://docs.nebius.com/serverless/quickstart/jobs)), sehingga GPU yang tersedia = platform GPU di region tersebut menurut [types](https://docs.nebius.com/compute/virtual-machines/types) dan [regions](https://docs.nebius.com/overview/regions):

| Region Serverless | Platform GPU tersedia |
| - | - |
| `eu-north1` | H200 (`gpu-h200-sxm`), H100 (`gpu-h100-sxm`), L40S Intel (`gpu-l40s-a`), L40S AMD (`gpu-l40s-d`) |
| `eu-west1` | H200 |
| `eu-west2` | B300 (`gpu-b300-sxm`) |
| `me-west1` | B200 (`gpu-b200-sxm-a`) |
| `us-central1` | B200 (`gpu-b200-sxm`), H200, RTX PRO 6000 (`gpu-rtx6000`) |
| `uk-south1` | B300 |
| `uk-south2` | RTX PRO 6000 (`gpu-rtx6000-a`) |
| CPU | cpu-d3 (AMD EPYC Genoa) di semua region; cpu-e2 (Intel) hanya `eu-north1` |

Catatan: beberapa platform GPU hanya ada di region tanpa Serverless AI (mis. B300 juga di `us-north1`; RTX6000-a juga di `eu-south1`), sehingga tidak otomatis dapat dipakai job ([types](https://docs.nebius.com/compute/virtual-machines/types), [regions](https://docs.nebius.com/overview/regions)).

Default platform CLI jika tidak ditentukan: `gpu-h100-sxm` di `eu-north1`, `gpu-h200-sxm` di region lain ([CLI create](https://docs.nebius.com/cli/reference/ai/job/create)) — untuk job CPU, platform/preset harus ditentukan eksplisit.

---

## 5. Implikasi untuk Mitra

> Bagian ini adalah **analisis (inferensi)** dari fakta yang dikutip di atas, bukan kutipan dokumentasi. Fakta pendukung tetap ditautkan.

### 5.1 Pro — Serverless Job

1. **Bayar hanya saat berjalan, per detik.** Tidak ada VM menganggur yang menagih biaya compute; VM dan container disk dihapus otomatis saat job selesai/gagal ([manage](https://docs.nebius.com/serverless/jobs/manage), [pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)). Inferensi: konsolidasi malam yang berjalan ±30–60 menit hanya menagih durasi itu, bukan 24 jam.
2. **Isolasi dari VM Mitra.** Setiap job berjalan di container VM terpisah ([manage](https://docs.nebius.com/serverless/jobs/manage)). Inferensi: konsolidasi tidak berebut CPU/RAM/disk dengan layanan Mitra yang berjalan di VM utama.
3. **Reproducibility & dependency bersih.** Workload dikemas sebagai image container; versi dependency tidak bergantung pada state VM ([manage](https://docs.nebius.com/serverless/jobs/manage)). Inferensi: hasil lebih konsisten antar-run dan tidak "mengotori" VM.
4. **Retry transien otomatis.** `--restart-policy on-failure` me-restart pada exit code non-zero (cocok dengan pekerjaan yang bisa lanjut dari checkpoint) ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts)).
5. **Integrasi secret & penyimpanan resmi.** Env sensitif via SecretStash/MysteryBox; hasil/checkpoint dapat ditulis ke bucket atau shared filesystem yang di-mount ([manage](https://docs.nebius.com/serverless/jobs/manage)).
6. **Tanpa markup Serverless.** Harga/kuota = Compute ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas)); parameter biaya lebih mudah diprediksi dari halaman harga Compute ([Compute pricing](https://docs.nebius.com/compute/resources/pricing)).
7. **Otomatisasi ramah skrip.** CLI deterministik + REST API memungkinkan trigger dari cron/CI mana pun yang punya kredensial ([manage](https://docs.nebius.com/serverless/jobs/manage), [REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create)).

### 5.2 Kontra — Serverless Job

1. **Tidak menghilangkan scheduler.** Tidak ada penjadwalan bawaan yang terdokumentasi (§2.3) — tetap perlu cron/timer/CI di suatu tempat yang memanggil API. Inferensi: jika VM tetap harus hidup hanya untuk memicu job, sebagian keuntungan "tanpa VM" hilang.
2. **Latensi mulai tidak instan.** Provisioning + pull image "usually takes a few minutes"; metrik baru muncul 5–10 menit; jika kapasitas kosong, tunggu hingga 30 menit lalu `ERROR` ([manage](https://docs.nebius.com/serverless/jobs/manage), [monitoring](https://docs.nebius.com/serverless/monitoring), [lifecycle](https://docs.nebius.com/serverless/lifecycle)). Inferensi: kurang cocok jika konsolidasi harus selesai tepat waktu / segera.
3. **Timeout minimum 1 jam.** Setting timeout tidak bisa di bawah 1 jam; job menggantung bisa berjalan (dan menagih) hingga timeout — default 24 jam jika tidak diubah ([CLI create](https://docs.nebius.com/cli/reference/ai/job/create), [manage](https://docs.nebius.com/serverless/jobs/manage)). Inferensi: perlu disiplin menetapkan timeout eksplisit dan idempotensi workload.
4. **Kapasitas tidak dijamin & tidak di-retry.** `NotEnoughResources`, preemption, VM stop, dan startup failure tidak ditangani `--restart-policy` ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts), [lifecycle](https://docs.nebius.com/serverless/lifecycle)). Inferensi: butuh alert/monitoring eksternal untuk menjalankan ulang, berbeda dari cron lokal yang selalu ada.
5. **Default `never`.** Tanpa konfigurasi, kegagalan konsolidasi langsung berakhir `FAILED` tanpa ulangan ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts)).
6. **Akses data harus dirancang.** Container disk job ephemeral; state harus lewat bucket/shared filesystem ber-mount, atau API; volume tidak otomatis terhapus ([manage](https://docs.nebius.com/serverless/jobs/manage)). Inferensi: jika konsolidasi Mitra membaca/menulis file lokal VM, perlu langkah migrasi data.
7. **Overhead operasional baru.** Butuh registry image (kredensial bila privat), subnet ID, IAM minimal `editor`, pipeline build/push, dan dua sistem untuk dirawat ([manage](https://docs.nebius.com/serverless/jobs/manage)). Inferensi: biaya engineering di awal lebih tinggi daripada cron+venv di VM.
8. **Log tidak tersedia via REST.** Log hanya console/CLI, membatasi otomasi pengumpulan log kegagalan ([manage](https://docs.nebius.com/serverless/jobs/manage)).
9. **Konsumsi kuota Compute.** Job menghitung kuota VM/GPU/vCPU; default beberapa GPU = 0 (mis. B200 di `me-west1`/`us-central1`) sehingga butuh kenaikan kuota bila ingin GPU ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits)).
10. **Preemptible tidak untuk CPU.** Varian murah preemptible hanya untuk platform GPU; job CPU berjalan di VM regular ([manage](https://docs.nebius.com/serverless/jobs/manage), [preemptible](https://docs.nebius.com/compute/virtual-machines/preemptible)).

### 5.3 Pertanyaan penentu (checklist keputusan)

- Apakah konsolidasi malam sudah/bisa dikemas sebagai container image? Jika tidak, biaya awal Serverless Job lebih tinggi ([manage](https://docs.nebius.com/serverless/jobs/manage)).
- Apakah state Mitra dapat diakses via Object Storage/shared filesystem atau API, bukan file lokal VM? ([manage](https://docs.nebius.com/serverless/jobs/manage))
- Berapa durasi tipikal dan maksimum yang dapat diterima? Ingat timeout minimum 1 jam ([CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).
- Apakah ada mesin lain yang tetap hidup 24/7 untuk memicu job (cron/CI)? Jika tidak, Serverless Job tidak menghapus kebutuhan scheduler ([§2.3](#23-penjadwalan)).
- Apakah toleransi terhadap kegagalan sesekali cukup dengan `on-failure` + alert manual, mengingat kapasitas/preemption tidak di-retry ([auto-restarts](https://docs.nebius.com/serverless/jobs/auto-restarts))?
- Apakah region proyek mendukung Serverless AI dan platform yang dibutuhkan (lihat §4; konfirmasi via console karena ada pertentangan dokumentasi) ([regions](https://docs.nebius.com/overview/regions))?

---

## 6. Sumber Resmi (diakses 2026-10-02)

1. [Managing jobs in Serverless AI](https://docs.nebius.com/serverless/jobs/manage)
2. [About Serverless AI](https://docs.nebius.com/serverless/overview)
3. [Serverless AI — index](https://docs.nebius.com/serverless/index)
4. [Getting started with Serverless AI jobs: Run nvidia-smi within a job](https://docs.nebius.com/serverless/quickstart/jobs)
5. [Lifecycle and statuses of Devlabs, endpoints and jobs](https://docs.nebius.com/serverless/lifecycle)
6. [Automatic job restarts](https://docs.nebius.com/serverless/jobs/auto-restarts)
7. [Debugging failed Devlabs, jobs and endpoints](https://docs.nebius.com/serverless/jobs/failure)
8. [Pricing and quotas in Serverless AI](https://docs.nebius.com/serverless/pricing-quotas)
9. [Metrics for endpoints and jobs](https://docs.nebius.com/serverless/monitoring)
10. [nebius ai job — CLI reference](https://docs.nebius.com/cli/reference/ai/job)
11. [nebius ai job create — CLI reference](https://docs.nebius.com/cli/reference/ai/job/create)
12. [Create job — REST API reference](https://docs.nebius.com/rest-api/ai/v1/jobs/create)
13. [Compute pricing in Nebius AI Cloud](https://docs.nebius.com/compute/resources/pricing)
14. [Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits)
15. [Types of virtual machines and GPUs in Nebius AI Cloud](https://docs.nebius.com/compute/virtual-machines/types)
16. [Preemptible virtual machines](https://docs.nebius.com/compute/virtual-machines/preemptible)
17. [Nebius AI Cloud regions](https://docs.nebius.com/overview/regions)
18. [Nebius AI Cloud documentation index (llms.txt)](https://docs.nebius.com/llms.txt)
19. [Nebius docs MCP endpoint (pencarian teks korpus docs)](https://docs.nebius.com/mcp)
20. [Nebius Python SDK — README](https://github.com/nebius/pysdk) (raw: [README.md](https://raw.githubusercontent.com/nebius/pysdk/refs/heads/main/README.md))
21. [Nebius API OpenAPI spec](https://api.nebius.cloud/openapi.json)
22. [Nebius web console](https://console.nebius.com) — dipakai untuk konfirmasi kuota/region aktual (tidak diakses dalam riset ini)

---

## 7. Yang Tidak Ditemukan

1. **Penjadwalan bawaan (cron/scheduler) untuk Serverless Jobs** — tidak ada halaman, perintah CLI, atau field dokumentasi yang menjelaskannya; hanya frasa "one-off or scheduled" tanpa mekanisme. Perlu konfirmasi support bila fitur ini menentukan keputusan ([manage](https://docs.nebius.com/serverless/jobs/manage), [CLI job](https://docs.nebius.com/cli/reference/ai/job), [llms.txt](https://docs.nebius.com/llms.txt)).
2. **Angka kapasitas fisik/throughput job per region** — tidak dipublikasikan; Capacity advisor yang ada hanya untuk VM GPU ([capacity advisor](https://docs.nebius.com/compute/virtual-machines/capacity-advisor)).
3. **Batas jumlah job konkuren khusus Serverless** — tidak ditemukan; yang berlaku adalah kuota Compute (VM/GPU/vCPU) ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [Quotas in Compute](https://docs.nebius.com/compute/resources/quotas-limits)).
4. **SLA/durasi maksimum menjamin ketersediaan kapasitas saat start** — hanya disebut percobaan 30 menit lalu `ERROR`, tanpa jaminan ([lifecycle](https://docs.nebius.com/serverless/lifecycle)).
5. **Aturan penagihan selama fase `PROVISIONING`/`IMAGE_PULLING`** — dokumen hanya menyatakan penagihan "while the job is running"; apakah provisioning/penungguan kapasitas ditagih tidak dinyatakan eksplisit `[BELUM TERVERIFIKASI]` ([pricing-quotas](https://docs.nebius.com/serverless/pricing-quotas), [manage](https://docs.nebius.com/serverless/jobs/manage)).
6. **Tipe disk default container job** — contoh REST memakai `NETWORK_SSD` dan disk default 250 GiB, tetapi default resmi tipe disk tidak dinyatakan eksplisit `[BELUM TERVERIFIKASI]` ([REST create](https://docs.nebius.com/rest-api/ai/v1/jobs/create), [CLI create](https://docs.nebius.com/cli/reference/ai/job/create)).
7. **Contoh resmi pembuatan job via SDK Python/Go/TypeScript** — README SDK menyatakan dukungan semua API, tetapi tidak ada contoh JobService yang saya temukan `[BELUM TERVERIFIKASI: binding SDK untuk ai job]` ([pysdk README](https://github.com/nebius/pysdk), [llms.txt](https://docs.nebius.com/llms.txt)).
8. **Log job via REST API** — secara eksplisit hanya console dan CLI ([manage](https://docs.nebius.com/serverless/jobs/manage)).
9. **Konsistensi klaim ketersediaan region Serverless AI** — halaman indeks ("all public regions") vs matriks region (`eu-south1`, `us-north1` tidak dicentang) `[BELUM TERVERIFIKASI]` ([serverless index](https://docs.nebius.com/serverless/index), [regions](https://docs.nebius.com/overview/regions)).
10. **Integrasi langsung job dengan layanan Mitra (mis. memanggil API internal Mitra di VPC yang sama)** — tidak dibahas di dokumentasi Serverless Jobs; menyangkut desain jaringan/subnet dan perlu diuji sendiri `[BELUM TERVERIFIKASI]` ([manage](https://docs.nebius.com/serverless/jobs/manage)).