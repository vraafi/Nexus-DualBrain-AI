---
name: fiverr-orders
description: "Monitor order Fiverr yang masuk, reply ke buyer, dan queue order untuk diproses oleh codegen skill. Berbeda dengan Upwork — di Fiverr kita menunggu order, bukan apply."
version: "1.0.0"
triggers:
  - "cek fiverr"
  - "fiverr orders"
  - "ada order fiverr"
  - "proses fiverr"
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

# Skill: Fiverr Order Monitor

## Tujuan
Cek order aktif di Fiverr, baca requirement dari buyer, kirim acknowledgment reply, dan antrekan order untuk diproses codegen.

## Langkah-Langkah

### 1. Cek order aktif via script
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/fiverr_orders_tool.py --action check_active
```
Output: JSON list order aktif dengan detail requirement.

### 2. Untuk setiap order baru (status: AWAITING_REQUIREMENTS atau NEW)

#### a. Baca riwayat buyer
```bash
read ~/.openclaw/memory/clients/fiverr/<buyer_username>.md
```

#### b. Generate reply acknowledgment
Buat pesan acknowledgment yang:
- Konfirmasi menerima order dan requirement
- Sebutkan timeline estimasi (contoh: "I'll deliver within 24 hours")
- Tanyakan clarifikasi HANYA jika requirement benar-benar tidak jelas
- Profesional dan ramah

#### c. Kirim reply
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/fiverr_orders_tool.py --action reply --order-id "<order_id>" --message "<ack_message>"
```

### 3. Antrekan untuk codegen
Tulis job data ke antrian:
```bash
write ~/Nexus-DualBrain-AI/output/job_queue.json
```
Format:
```json
{
  "platform": "fiverr",
  "order_id": "<id>",
  "buyer": "<username>",
  "title": "<gig_title>",
  "description": "<requirement>",
  "budget": <amount>,
  "deadline_hours": <hours>,
  "status": "QUEUED"
}
```

### 4. Update memori buyer
```bash
write ~/.openclaw/memory/clients/fiverr/<buyer_username>.md
```
Tambahkan: tanggal order, judul gig, status

### 5. Catat ke finansial tracker
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/finance_tool.py --action log_proposal --platform fiverr --title "<gig_title>" --budget <amount>
```

## Aturan Penting
- Fiverr: JANGAN pernah kirim deliverable di luar platform (no email, no Google Drive langsung)
- Reply dalam 1 jam pertama = meningkatkan rating response time di Fiverr
- Jika buyer minta revisi: update file job_queue.json dengan status REVISION

## Output yang Diharapkan
- File `output/job_queue.json` diupdate dengan order baru
- Reply acknowledgment terkirim ke buyer
- Notifikasi Telegram: jumlah order baru yang masuk
