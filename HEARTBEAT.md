# Nexus DualBrain AI — HEARTBEAT.md
# OpenClaw membaca file ini setiap 30 menit dan menjalankan task yang terjadwal.
# Gunakan waktu eksplisit (HH:MM) bukan kata ambigu seperti "pagi".

## Jadwal Harian (WIB)

### 17:00 - 01:00 WIB — Sesi Fiverr & X (Twitter)
- **17:00**: Mulai sesi kerja setelah istirahat siang. Cek status PAUSED.
- **Fiverr**: Mengecek order aktif, membuat penawaran di pembeli yang potensial (`search_and_offer_gigs`).
- **X (Twitter) Fallback**: Jika tidak ada interaksi di Fiverr, bot beralih mencari cuitan/postingan tentang kebutuhan *coding* dan membalas dengan menawarkan diri, serta menjadwalkan pembuatan postingan berita teknologi yang mengandung komedi/informatif.
- **Inbox Check**: Mengawasi `EmailMonitor` yang akan selalu menyela jika ada order masuk.

### 01:00 - 11:00 WIB — Sesi Upwork
- **01:00**: Ganti platform ke Upwork.
- **Upwork Search**: Mencari pekerjaan *Python/automation* baru (`scrape_jobs`).
- Mengirimkan CV/Cover Letter secara otonom ke hasil yang memenuhi syarat `is_autonomous`.
- Log hasilnya ke `memory/sessions/`.

### 11:00 - 17:00 WIB — Jam Istirahat
- Sistem memasuki fase tidur (`wait_until_active`).
- Menyimpan semua state ke database dan memberhentikan aktivitas *search* dan pengiriman proposal.
- Klien Amerika rata-rata tidur pada jam ini (malam hari EST/PST).

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
