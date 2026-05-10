---
name: memory-client
description: "Baca dan tulis memori per-klien. Setiap klien punya file Markdown sendiri berisi riwayat interaksi, preferensi, job history, dan catatan penting. Dipanggil oleh skill lain, bukan langsung oleh user."
version: "1.0.0"
triggers:
  - "simpan memori klien"
  - "baca profil klien"
  - "update klien"
tools:
  - read
  - write
permissions:
  - file_read
  - file_write
---

# Skill: Per-Client Memory Management

## Tujuan
Mengelola file memori per-klien di `~/.openclaw/memory/clients/<platform>/<username>.md`.
Dipanggil oleh skill lain untuk membaca konteks klien sebelum berinteraksi, atau menulis hasil interaksi.

## Struktur File Memori Klien

Setiap file klien mengikuti template berikut:

```markdown
# Client: <username> (<platform>)

## Info Dasar
- Platform: <upwork|fiverr|freelancer>
- Username: <username>
- Nama: <first name jika diketahui>
- Rating: <rating jika ada>
- Lokasi: <timezone/country jika diketahui>
- Bahasa: <bahasa komunikasi yang disukai>

## Riwayat Job
| Tanggal | Job Title | Budget | Status | Revenue |
|---|---|---|---|---|
| <date> | <title> | $<amount> | <DELIVERED/CANCELLED> | $<actual> |

## Preferensi & Catatan
- <catatan penting tentang gaya komunikasi>
- <format deliverable yang disukai>
- <hal yang perlu dihindari>
- <feedback atau komplain sebelumnya>

## Riwayat Negosiasi
- <date>: <ringkasan interaksi negosiasi>
- <date>: <ringkasan>

## Status Saat Ini
- Status: <PROSPECT|ACTIVE|DELIVERED|INACTIVE>
- Job aktif: <job_title atau "tidak ada">
- Last contact: <date>
```

## Cara Membaca Memori Klien

```bash
read ~/.openclaw/memory/clients/<platform>/<username>.md
```

Jika file tidak ada, buat baru dengan template di atas menggunakan info minimal yang tersedia.

## Cara Menulis/Update Memori Klien

Setelah setiap interaksi, update file dengan:
1. Tambahkan baris ke tabel Riwayat Job (jika ada perubahan status job)
2. Tambahkan catatan ke Riwayat Negosiasi
3. Update Status Saat Ini
4. Tambahkan preferensi baru ke Preferensi & Catatan

```bash
write ~/.openclaw/memory/clients/<platform>/<username>.md
```

## Aturan Penting
- Jangan hapus entri lama dari riwayat — append saja
- Jika ada info baru tentang preferensi klien, tambahkan ke bagian Preferensi
- File ini adalah "ingatan jangka panjang" agent tentang klien ini
- Ukuran file maksimal: ~50KB (jika lebih, ringkas riwayat lama)

## Output
- File memori klien dibuat atau diupdate
- Tidak ada notifikasi Telegram (skill internal)
