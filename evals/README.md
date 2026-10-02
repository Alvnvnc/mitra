# Evals — pengujian model (v0)

Tujuan: memilih dan memantau model Nemotron per peran (fast / chat / reasoning) dengan
**check objektif**, bukan kesan. Ini juga bahan bukti proses untuk submission.

## Cara jalan

```bash
.venv/bin/python evals/run_evals.py                 # semua kasus
.venv/bin/python evals/run_evals.py --case tool-reminder
.venv/bin/python evals/run_evals.py --models-all    # debug: semua model di semua kasus
```

Output:
- ringkasan di terminal (lulus/gagal per model + biaya)
- hasil mentah JSON di `evals/results/` (gitignored)

## Aturan disiplin

1. **Kasus dibekukan setelah dipakai.** Kalau perlu berubah, buat versi baru — jangan edit
   kasus yang sudah pernah dipakai untuk klaim hasil.
2. **Check objektif dulu.** Exact/label/JSON/tool-call. LLM judge menyusul hanya bila tak
   terhindarkan (dan dicatat sebagai keterbatasan).
3. **Output mentah disimpan.** Ringkasan boleh dikutip; angka mentah tetap ada.
4. **Biaya dicatat** per panggilan (estimasi dari tabel harga Token Factory).
5. Kasus diturunkan dari pola nyata di `docs/COMMUNITY_RESEARCH.md` — bukan soal karangan.

## Hasil run pertama (2026-10-02, v0)

13/14 lulus · 14 panggilan · biaya ~$0.0021.

| Model | Hasil | Catatan |
|---|---|---|
| Nano 30B | 4/4 | JSON ekstraksi + resolusi versi aktif — kuat untuk peran *fast* |
| Super 120B | 3/3 | Termasuk **function calling** (memilih `scheduler_add` / `web_search`) dan tidak mengklaim aksi yang tidak bisa dilakukan |
| Ultra 550B | 3/3 | Aritmetika & selisih jam benar |
| 3.5 Lightning | 2/3 | **Gagal structured output**: reasoning bocor ke `content` ("Here's a thinking process…") alih-alih JSON — butuh panduan system prompt / budget token; jadikan kasus lanjutan (jangan ubah kasus lama) |

Temuan sampingan: biaya 14 panggilan ≈ $0.002 — pengujian model praktis gratis pada skala ini.

## Keterbatasan v0

- Jumlah kasus kecil (10) — arah, bukan pemeringkatan final.
- Belum ada uji lintas sesi (butuh mekanisme memori; menyusul di W2/W3).
- Kasus berbahasa Indonesia; model mungkin lebih kuat dalam Inggris (catatan, bukan bug).