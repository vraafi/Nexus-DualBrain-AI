---
name: negotiate
description: "Baca pesan dari klien di semua platform, klasifikasi intent (negosiasi harga, clarifikasi, revision request, acceptance), dan buat respons yang tepat menggunakan konteks riwayat klien dari memori."
version: "1.0.0"
triggers:
  - "cek inbox"
  - "ada pesan"
  - "check messages"
  - "negosiasi"
  - "reply klien"
  - "balas pesan"
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

# Skill: Negotiation & Client Communication

## Tujuan
Memproses semua pesan masuk dari klien di Upwork, Fiverr, dan Freelancer, mengklasifikasi intent, dan generate respons yang tepat berdasarkan konteks dan riwayat klien.

## Langkah-Langkah

### 1. Ambil semua pesan baru dari semua platform
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/inbox_tool.py --platform all --action check_new
```
Output: JSON list pesan baru dengan metadata (platform, sender, thread_id, content, timestamp).

### 2. Untuk setiap pesan, baca riwayat klien
```bash
read ~/.openclaw/memory/clients/<platform>/<username>.md
```

### 3. Klasifikasi intent pesan
Gunakan reasoning untuk mengklasifikasikan pesan ke salah satu kategori:
- `PRICE_NEGOTIATION` — klien minta diskon atau negosiasi harga
- `CLARIFICATION` — klien minta penjelasan tentang proposal/deliverable
- `REVISION_REQUEST` — klien minta perubahan setelah delivery
- `CONTRACT_ACCEPTANCE` — klien setuju dan siap mulai kontrak
- `GENERAL_QUESTION` — pertanyaan umum tentang kemampuan/pengalaman
- `COMPLAINT` — klien tidak puas
- `PAYMENT_ISSUE` — masalah pembayaran

### 4. Generate respons berdasarkan kategori

#### PRICE_NEGOTIATION
- Jangan langsung kasih diskon
- Tawarkan nilai tambah dulu (lebih cepat, lebih banyak revisi, bonus fitur kecil)
- Jika diperlukan, turunkan maksimal 15% dari harga awal
- Gunakan framing: "For [their budget], I can deliver [adjusted scope]"

#### CLARIFICATION
- Jawab dengan jelas dan teknis
- Jika sudah ada dalam proposal, re-explain dengan lebih detail
- Sertakan contoh konkret jika membantu

#### REVISION_REQUEST
- Terima dengan profesional
- Konfirmasi scope revisi yang diminta
- Set expectation timeline revisi
- Update job_queue.json dengan status REVISION

#### CONTRACT_ACCEPTANCE
- Konfirmasi acceptance dengan antusias tapi profesional
- Tanyakan start date preferensi klien
- Trigger skill `05-codegen` untuk mulai generate kode

#### GENERAL_QUESTION
- Jawab dengan percaya diri
- Sertakan contoh relevan dari pengalaman (generate dari konteks skill)

#### COMPLAINT
- Empathize dulu, jangan defensif
- Tanyakan spesifiknya apa yang kurang
- Tawarkan solusi konkret
- Eskalasi ke user via Telegram jika terlalu kompleks

#### PAYMENT_ISSUE
- Arahkan ke mekanisme platform resmi
- Notifikasi user via Telegram segera

### 5. Kirim respons
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/inbox_tool.py --platform <platform> --action reply --thread-id "<thread_id>" --message "<response_text>"
```

### 6. Update memori klien
Tulis ke `~/.openclaw/memory/clients/<platform>/<username>.md`:
- Timestamp interaksi terbaru
- Intent yang terdeteksi
- Ringkasan response yang dikirim
- Status negosiasi saat ini

### 7. Jika CONTRACT_ACCEPTANCE: trigger codegen
Tulis ke `output/job_queue.json` dengan status ACCEPTED, lalu informasikan ke user:
"Kontrak diterima dari <client> di <platform>. Memulai code generation."

## Prinsip Negosiasi
- Selalu profesional, tidak pernah emosional
- Gunakan data/angka dalam argumen ("This typically takes 8 hours of development")
- Jangan pernah menjanjikan hal yang tidak bisa dikerjakan AI otonom
- Jika job butuh akses yang tidak dimiliki agent, jujur dan informasikan user

## Output
- Semua pesan baru dibalas
- Memori klien diupdate
- job_queue.json diupdate jika ada contract acceptance atau revision
- Notifikasi Telegram: ringkasan aktivitas inbox
