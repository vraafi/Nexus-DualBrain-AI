---
name: freelancer-search
description: "Cari dan bid pada job di Freelancer.com. Slot rotasi terpendek (5 jam), fokus pada job dengan persaingan rendah dan budget reasonable."
version: "1.0.0"
triggers:
  - "cari job freelancer"
  - "freelancer.com"
  - "bid freelancer"
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

# Skill: Freelancer.com Job Search

## Tujuan
Mencari job Python/scripting di Freelancer.com, filter berdasarkan kompetisi dan budget, bid dengan nilai kompetitif.

## Langkah-Langkah

### 1. Jalankan script pencarian
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/freelancer_search_tool.py
```
Output: JSON list job yang sudah difilter dan disortir.

### 2. Baca hasil
Baca file: `~/Nexus-DualBrain-AI/output/freelancer_jobs.json`

### 3. Untuk setiap job yang lolos filter

#### a. Cek riwayat employer
```bash
read ~/.openclaw/memory/clients/freelancer/<employer_username>.md
```

#### b. Generate bid
Buat bid yang:
- Dimulai dengan pemahaman mendalam tentang problem spesifik mereka
- Sebutkan pendekatan teknis singkat (3-4 kalimat)
- Cantumkan timeline realistis
- Bid amount: sedikit di bawah rata-rata bid lain (strategis)
- Panjang: 120-200 kata

#### c. Submit bid
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/freelancer_apply_tool.py --job-id "<job_id>" --bid-amount <amount> --proposal "<text>"
```

### 4. Catat
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/finance_tool.py --action log_proposal --platform freelancer --title "<job_title>" --budget <budget>
```

## Kriteria Filter
- Budget: minimal $25 fixed-price atau $10/jam
- Jumlah bid bersaing: maksimal 20 bid (lebih sedikit = peluang lebih besar)
- Skill match: Python, scripting, automation, data, bot
- Employer verification: preferably verified payment

## Output
- File `output/freelancer_jobs.json`
- Bid terkirim
- Notifikasi Telegram: ringkasan bid
