# Nexus DualBrain AI — HEARTBEAT.md
# OpenClaw membaca file ini setiap 30 menit dan menjalankan task yang terjadwal.
# Gunakan waktu eksplisit (HH:MM) bukan kata ambigu seperti "pagi".

## Jadwal Harian (WIB)

### 17:00 — Mulai Sesi Kerja
- Cek apakah agent dalam status PAUSED. Jika tidak, mulai siklus kerja.
- Jalankan skill `04-negotiate`: cek semua inbox (Upwork, Fiverr, Freelancer)
- Kirim ringkasan ke Telegram: "🌅 Sesi kerja dimulai. Cek inbox..."

### 18:00 — Upwork Search
- Jalankan skill `01-upwork-search`: cari job Python/automation baru
- Log hasilnya ke memory/sessions/

### 21:00 — Fiverr Check
- Jalankan skill `02-fiverr-orders`: cek order aktif Fiverr
- Proses order baru jika ada

### 23:00 — Freelancer Search
- Jalankan skill `03-freelancer-search`: bid pada job baru di Freelancer
- Log hasilnya

### 02:00 — Code Generation & Sandbox
- Baca job_queue.json untuk job dengan status ACCEPTED atau REVISION
- Jika ada: jalankan skill `05-codegen` lalu `06-sandbox-test`
- Notifikasi Telegram hasilnya

### 05:00 — Delivery
- Baca job_queue.json untuk job dengan status SANDBOX_PASSED
- Jalankan skill `07-deliver`
- Update financial tracker

### 08:00 — Laporan Pagi
- Kirim ringkasan ke Telegram:
  * Jumlah proposal terkirim hari ini
  * Jumlah job aktif
  * Pendapatan pending
  * Error yang perlu perhatian

### 10:30 — Persiapan Istirahat
- Simpan semua state ke database
- Pastikan tidak ada browser process yang masih berjalan
- Kirim notifikasi: "😴 Masuk jam istirahat dalam 30 menit."

## Task Kontinu (dijalankan setiap check jika ada trigger)

### Email Priority Check
- Setiap kali heartbeat jalan: cek apakah EmailMonitor punya pending order
- Jika ada: handle segera sebelum task lain, kirim notifikasi Telegram

### Resource Guard
- Sebelum setiap task berat: pastikan RAM < 85% dan CPU < 90%
- Jika resources kritis: tunda task 10 menit lalu coba lagi

### Circuit Breaker Monitor
- Jika circuit breaker platform manapun dalam status OPEN:
  kirim notifikasi Telegram: "⚠️ [Platform] circuit breaker OPEN — UI mungkin berubah"
