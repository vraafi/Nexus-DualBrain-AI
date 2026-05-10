---
name: codegen
description: "Generate kode Python lengkap menggunakan Gemini 2.5 Pro dengan web search otomatis untuk dokumentasi terkini. Input: job description dari job_queue.json. Output: file Python siap di-test."
version: "1.0.0"
triggers:
  - "generate kode"
  - "buat kode"
  - "codegen"
  - "tulis script"
  - "mulai coding"
tools:
  - exec
  - read
  - write
permissions:
  - file_write
  - shell_exec
---

# Skill: Code Generation (Gemini 2.5 Pro)

## Tujuan
Mengambil job dari antrian (job_queue.json), generate kode Python lengkap menggunakan Gemini 2.5 Pro dengan thinking mode HIGH, dan simpan ke file untuk di-test.

## Langkah-Langkah

### 1. Baca job dari antrian
```bash
read ~/Nexus-DualBrain-AI/output/job_queue.json
```
Ambil job dengan status `ACCEPTED` atau `REVISION` (prioritas: REVISION lebih dulu).

### 2. Baca riwayat klien untuk konteks tambahan
```bash
read ~/.openclaw/memory/clients/<platform>/<username>.md
```

### 3. Jalankan code generation
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/codegen_tool.py \
  --job-id "<job_id>" \
  --title "<job_title>" \
  --description "<job_description>" \
  --platform "<platform>" \
  --output-dir output/generated/
```

Script ini menggunakan Gemini 2.5 Pro dengan:
- `thinkingBudget: 8192` (thinking mode tinggi)
- Web search otomatis jika butuh dokumentasi terkini
- Self-contained code dengan unit tests di bagian bawah
- Output: file Python + metadata JSON

### 4. Verifikasi output
Baca file yang dihasilkan:
```bash
read ~/Nexus-DualBrain-AI/output/generated/<job_id>_code.py
```

Pastikan:
- File tidak kosong
- Tidak ada placeholder seperti `TODO` atau `YOUR_API_KEY_HERE` (kecuali memang dibutuhkan oleh job)
- Ada unit tests di bagian bawah
- Import libraries tersedia (tidak ada import yang obscure dan tidak bisa diinstall)

### 5. Jika kode ada placeholder atau tidak lengkap
Jalankan ulang dengan prompt yang lebih spesifik:
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/codegen_tool.py \
  --job-id "<job_id>" \
  --retry \
  --feedback "Kode tidak lengkap, ada TODO pada bagian: <bagian yang kurang>"
```

### 6. Update status job queue
Update `output/job_queue.json`: status → `CODE_READY`, path kode → `output/generated/<job_id>_code.py`

### 7. Notifikasi
Kirim ke Telegram: "Kode untuk '<job_title>' selesai digenerate. Memulai sandbox testing..."

## Standar Kualitas Kode yang Dihasilkan
- Bahasa: Python 3.10+
- Error handling: try/except pada semua operasi I/O dan network
- Logging: gunakan modul `logging`, bukan `print()`
- Unit tests: minimal 3 test cases menggunakan `unittest`
- Dependencies: hanya library standar + requests, beautifulsoup4, atau yang umum tersedia
- Dokumentasi: docstring pada setiap fungsi utama

## Model yang Digunakan
- Gemini 2.5 Pro (`gemini-2.5-pro`) dengan thinking mode HIGH
- Fallback: Gemini 2.5 Flash jika Pro rate-limited

## Output
- File kode: `output/generated/<job_id>_code.py`
- Metadata: `output/generated/<job_id>_meta.json`
- job_queue.json diupdate: status CODE_READY
