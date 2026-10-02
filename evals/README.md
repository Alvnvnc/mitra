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
| 3.5 Lightning | 2/3 | **Gagal structured output**: reasoning bocor ke `content` ("Here's a thinking process…") alih-alih JSON — butuh panduan system prompt / budget token; jadikan kasus lanjutan (jangan ubah kasus lama) → **diperbaiki & teruji, lihat bagian berikutnya** |

Temuan sampingan: biaya 14 panggilan ≈ $0.002 — pengujian model praktis gratis pada skala ini.

## Perbaikan teruji — Lightning structured output (2026-10-02)

Kasus `extract-schedule-json` gagal di v0 (reasoning bocor ke `content`). Lima pendekatan diuji
sebagai kasus baru (v2–v6); kasus lama tidak diubah:

| Kasus | Pendekatan | Hasil | Output tokens | Biaya |
|---|---|---|---|---|
| v2 | `response_format=json_object` | ❌ | (gagal) | — |
| v3 | `guided_json` via `extra_body` | ❌ | (gagal) | — |
| v4 | `max_tokens=1600` (thinking selesai dulu) | ✅ | 1.113 | $0.000271 |
| v5 | system prompt ketat + `response_format` | ✅ | 470 | $0.000118 |
| **v6** | **`extra_body={"chat_template_kwargs": {"enable_thinking": false}}`** | ✅ | **19** | **$0.000008** |

**Rekomendasi:** v6 untuk task terstruktur/cepat di Lightning — output bersih, tanpa
`reasoning_content`, ≈15× lebih hemat dari v5 dan ≈34× dari v4. v5 sebagai fallback yang tidak
bergantung pada dukungan provider. Hindari v4 kecuali terpaksa.
`ModelRouter.complete()` kini menerima `extra_body` untuk pola ini.

## Keterbatasan v0

- Jumlah kasus kecil (10) — arah, bukan pemeringkatan final.
- Belum ada uji lintas sesi (butuh mekanisme memori; menyusul di W2/W3).
- Kasus berbahasa Indonesia; model mungkin lebih kuat dalam Inggris (catatan, bukan bug).