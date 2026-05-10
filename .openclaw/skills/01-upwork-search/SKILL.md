---
name: upwork-search
description: "Cari job Python/coding di Upwork, filter yang bisa dikerjakan AI agent otonom, dan kirim proposal yang dipersonalisasi menggunakan browser Extension Relay (session login asli)."
version: "1.0.0"
triggers:
  - "cari job upwork"
  - "search upwork"
  - "upwork job"
  - "cari pekerjaan"
  - "mulai cari job"
tools:
  - browser
  - exec
  - read
  - write
permissions:
  - browser_control
  - file_write
  - shell_exec
---

# Skill: Upwork Job Search

## Tujuan
Mencari job Python/automation/scripting di Upwork yang sesuai untuk dikerjakan AI agent otonom, filter berdasarkan kriteria keberhasilan, dan kirim proposal yang dipersonalisasi.

## Langkah-Langkah

### 1. Jalankan script Python untuk pencarian job
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/upwork_search_tool.py
```
Script akan output JSON berisi daftar job yang sudah difilter. Baca hasilnya.

### 2. Baca hasil pencarian
Baca file output: `~/Nexus-DualBrain-AI/output/upwork_jobs.json`

### 3. Untuk setiap job yang lolos filter
Cek apakah klien punya riwayat di memori:
```bash
read ~/.openclaw/memory/clients/upwork/<client_username>.md
```

### 4. Generate proposal menggunakan konteks klien
Buat proposal yang dipersonalisasi berdasarkan:
- Deskripsi job
- Riwayat klien (jika ada di memori)
- Branding strategy Upwork dari `tools/branding_config.json`

Proposal harus:
- Dimulai dengan hook spesifik tentang problem mereka (bukan "Hello, I'm a developer")
- Panjang 150-250 kata
- Menyebutkan satu contoh relevan atau pengalaman spesifik
- Diakhiri dengan pertanyaan yang mendorong reply

### 5. Kirim proposal via script
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/upwork_apply_tool.py --job-id "<job_id>" --proposal "<proposal_text>"
```

### 6. Catat ke finansial tracker
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/finance_tool.py --action log_proposal --platform upwork --title "<job_title>" --budget <budget>
```

### 7. Simpan ke memori
Setelah apply, tulis ringkasan ke file log:
```bash
write ~/.openclaw/memory/sessions/upwork_$(date +%Y%m%d).md
```
Isi: tanggal, job title, budget, status APPLIED

## Kriteria Filter Job (WAJIB)
Hanya apply jika semua kondisi terpenuhi:
- Budget: minimal $30 untuk fixed-price, minimal $15/jam untuk hourly
- Kategori: Python, automation, scripting, web scraping, data processing, bot
- Deskripsi cukup jelas untuk dipahami dan dikerjakan oleh AI
- Bukan proyek yang butuh hardware fisik, akun personal, atau NDA sensitif
- Client rating minimal 4.0 jika sudah pernah hire sebelumnya

## Aturan Stealth
- Gunakan Extension Relay Mode (session Chrome yang sudah login)
- Jeda 3-8 detik acak antar aksi browser
- Jangan apply lebih dari 10 job per sesi
- Jeda minimal 30 menit antar sesi pencarian

## Output yang Diharapkan
- File `output/upwork_jobs.json` berisi job yang ditemukan
- Log proposal terkirim
- Notifikasi Telegram: jumlah job ditemukan + jumlah proposal terkirim
