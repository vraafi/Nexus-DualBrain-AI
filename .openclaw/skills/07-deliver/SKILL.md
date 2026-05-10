---
name: deliver
description: "Kirim hasil kerja (kode Python) ke klien di platform asal (Upwork/Fiverr/Freelancer) menggunakan browser Extension Relay. Sertakan pesan delivery profesional dan minta review jika sesuai."
version: "1.0.0"
triggers:
  - "deliver"
  - "kirim hasil"
  - "kirim kode"
  - "submit pekerjaan"
  - "delivery"
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

# Skill: Work Delivery

## Tujuan
Mengirimkan hasil kerja yang sudah lulus sandbox testing ke klien di platform asal. Generate pesan delivery yang profesional, upload file kode, dan minta review bintang 5 jika timing tepat.

## Langkah-Langkah

### 1. Baca job queue untuk job SANDBOX_PASSED
```bash
read ~/Nexus-DualBrain-AI/output/job_queue.json
```
Ambil job dengan status `SANDBOX_PASSED`.

### 2. Baca riwayat klien
```bash
read ~/.openclaw/memory/clients/<platform>/<username>.md
```

### 3. Generate pesan delivery
Buat pesan delivery yang:
- Sapa klien dengan nama (jika ada di memori)
- Jelaskan secara singkat apa yang dikerjakan dan pendekatan yang diambil
- Sebutkan bahwa kode sudah ditest dan berfungsi
- Instruksi cara menjalankan (jika perlu)
- Tawaran revisi jika ada yang perlu disesuaikan
- Hindari kalimat generik seperti "Here is your code"
- Panjang: 100-180 kata

### 4. Kirim via script delivery
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/delivery_tool.py \
  --platform "<platform>" \
  --job-id "<job_id>" \
  --order-id "<order_id>" \
  --code-path "output/generated/<job_id>_final.py" \
  --message "<delivery_message>"
```

### 5. Verifikasi delivery berhasil
Baca output script untuk konfirmasi:
- Status HTTP 200 atau success indicator
- Tidak ada error

### 6. Jika delivery berhasil
Update job_queue.json: status → `DELIVERED`
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/finance_tool.py \
  --action update_status \
  --title "<job_title>" \
  --status DELIVERED \
  --revenue <budget_amount>
```

Update memori klien — tambahkan:
- Tanggal delivery
- Status: DELIVERED
- Judul job
- Revenue

### 7. Jika delivery gagal (browser error / platform error)
Coba ulang 1x setelah 5 menit:
```bash
sleep 300
cd ~/Nexus-DualBrain-AI && python3 tools/delivery_tool.py --retry --job-id "<job_id>"
```
Jika masih gagal: notifikasi Telegram "PERLU INTERVENSI MANUAL: Delivery gagal untuk '<job_title>'"

### 8. Notifikasi final
```bash
Telegram: "✅ DELIVERED: '<job_title>' ke <username> di <platform>. Revenue: $<amount>"
```

## Aturan Platform

### Upwork
- Kirim melalui halaman Messages di contract
- Gunakan tombol "Submit Work" jika tersedia
- Attachment: upload file .py langsung

### Fiverr
- Gunakan tombol "Deliver Now" di halaman order
- WAJIB klik "Deliver Now" — jangan hanya kirim pesan
- Attachment: upload file .py atau .zip

### Freelancer.com
- Kirim melalui Project Workroom
- Update milestone jika ada
- Upload file di thread proyek

## Timing Minta Review
Minta review HANYA jika:
- Klien membalas dengan positif setelah delivery
- Atau 24 jam setelah delivery tanpa komplain
- Jangan minta review di pesan delivery pertama (terlalu agresif)

## Output
- job_queue.json: status DELIVERED
- financial_tracker: revenue dicatat
- Memori klien: diupdate
- Notifikasi Telegram: konfirmasi delivery
