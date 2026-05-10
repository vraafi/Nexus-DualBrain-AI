# Panduan Menjalankan AI Agent di Windows untuk Pemula

Halo! Selamat datang. Jika kamu pengguna Windows yang belum pernah menggunakan terminal atau menginstal kode apa pun, jangan khawatir. Panduan ini dibuat khusus untuk kamu agar bisa menjalankan AI Agent ini langkah demi langkah.

AI Agent ini dirancang untuk berjalan di sistem operasi Linux karena menggunakan fitur keamanan khusus bernama `bubblewrap` (`bwrap`) untuk melakukan *sandbox testing* (pengujian kode secara aman agar tidak merusak komputermu). Tapi tenang, kamu tidak perlu mengganti Windows kamu dengan Linux! Kita akan menggunakan **WSL (Windows Subsystem for Linux)**, yaitu fitur resmi dari Microsoft yang memungkinkan kita menjalankan Linux di dalam Windows.

Mari kita mulai!

---

## Langkah 1: Mengaktifkan WSL (Windows Subsystem for Linux)

WSL adalah cara paling mudah untuk menjalankan perintah Linux di Windows.

1. Buka **Start Menu** di Windows kamu.
2. Ketik **PowerShell**, lalu klik kanan pada **Windows PowerShell** dan pilih **"Run as administrator"** (Jalankan sebagai administrator). Klik "Yes" jika muncul peringatan.
3. Di jendela PowerShell yang berwarna biru atau hitam, ketikkan perintah berikut persis seperti ini, lalu tekan **Enter**:
   ```powershell
   wsl --install
   ```
   *(Tips: Jika kamu tidak bisa menempelkan (paste) teks ke PowerShell menggunakan klik kanan, coba gunakan kombinasi tombol **Ctrl + V** di keyboard. Atau, klik kanan pada bingkai/judul jendela PowerShell di bagian paling atas, pilih **Properties**, centang opsi **"Use Ctrl+Shift+C/V as Copy/Paste"** atau **"QuickEdit Mode"**, lalu klik OK.)*
4. Tunggu proses instalasi selesai. Ini akan mengunduh dan menginstal "Ubuntu" (salah satu versi Linux paling populer).
5. Setelah selesai, **Restart (mulai ulang) komputer kamu**.

## Langkah 2: Mengatur Ubuntu (Linux di Windows)

Setelah komputer menyala kembali:

1. Buka **Start Menu**, cari **Ubuntu**, dan buka aplikasinya.
2. Jendela terminal hitam akan muncul. Tunggu beberapa saat sampai instalasi awal selesai.
3. Kamu akan diminta membuat **username** (nama pengguna) baru untuk Ubuntu (misalnya namamu dengan huruf kecil semua tanpa spasi). Tekan Enter.
4. Selanjutnya, masukkan **password**. *Catatan: Saat kamu mengetik password, hurufnya tidak akan muncul di layar (itu normal demi keamanan). Ketik saja passwordmu lalu tekan Enter.* Ketik ulang password untuk konfirmasi dan tekan Enter lagi.
5. Selamat! Sekarang kamu sudah berada di dalam lingkungan Linux (Ubuntu).

## Langkah 3: Menyiapkan Program yang Dibutuhkan

Di dalam terminal Ubuntu yang masih terbuka, kita perlu menginstal beberapa perangkat lunak dasar. Kita akan menggunakan perintah yang diawali dengan `sudo` (seperti "Run as administrator" di Windows).

1. Perbarui daftar paket aplikasi dengan mengetik perintah berikut dan tekan Enter:
   ```bash
   sudo apt-get update
   ```
   *(Kamu mungkin akan diminta memasukkan password Ubuntu yang baru saja kamu buat. Ingat, ketikannya tidak akan terlihat.)*

2. Instal alat yang dibutuhkan oleh AI Agent (termasuk `bubblewrap`, `python3-venv`, dan `python3-pip`) dengan mengetik:
   ```bash
   sudo apt-get install -y bubblewrap python3-venv python3-pip git
   ```
   Tunggu hingga proses pengunduhan dan instalasi selesai.

## Langkah 4: Mengunduh AI Agent (Clone Repository)

Sekarang kita akan mengunduh kode AI Agent ini ke dalam komputer kamu.

1. Pindah ke direktori utama (Home) agar aman dari masalah perizinan (permission):
   ```bash
   cd ~
   ```

2. Di terminal Ubuntu, ketik perintah berikut dan tekan Enter:
   ```bash
   git clone https://github.com/vraafi/Nexus-DualBrain-AI.git ai-agent
   ```

## Langkah 5: Menginstal Dependensi (Bahan-bahan yang Dibutuhkan AI)

Pastikan kamu masuk ke dalam folder AI Agent di terminal Ubuntu.

1. Masuk ke folder:
   ```bash
   cd ai-agent
   ```

2. Buat lingkungan virtual khusus (virtual environment) agar sistem komputer utama kamu tetap bersih:
   ```bash
   python3 -m venv venv
   ```

3. Aktifkan lingkungan virtual tersebut:
   ```bash
   source venv/bin/activate
   ```
   *(Setelah perintah ini berhasil, kamu akan melihat tulisan `(venv)` muncul di bagian paling kiri baris terminal kamu).*

4. Instal bahan-bahan Python yang dibutuhkan dengan mengetik:
   ```bash
   pip install -r requirements.txt
   ```
   Tunggu sampai semuanya selesai.

2. Instal browser Chromium khusus yang digunakan AI untuk berselancar di internet:
   ```bash
   playwright install chromium
   ```

## Langkah 6: Konfigurasi AI Agent (Penting!)

AI Agent butuh kunci (API Key) agar bisa berpikir dan terhubung dengan Telegram.

1. Gandakan file contoh konfigurasi dengan mengetik:
   ```bash
   cp .env.example .env
   ```
2. Buka file konfigurasi (`.env`) menggunakan editor teks sederhana di terminal bernama `nano`:
   ```bash
   nano .env
   ```
3. Di dalam editor `nano`, gunakan tombol panah (atas/bawah/kiri/kanan) di keyboard untuk berpindah kursor. Isi bagian-bagian ini:
   - `GEMINI_KEY_1=...` (Dapatkan dari [Google AI Studio](https://aistudio.google.com/apikey))
   - `TELEGRAM_BOT_TOKEN=...` (Dapatkan dari [@BotFather](https://t.me/BotFather) di Telegram)
   - `TELEGRAM_CHAT_ID=...` (Dapatkan dari bot @userinfobot di Telegram)
   - `VAULT_PASSWORD=...` (Buat password acak yang kuat, minimal 16 karakter. Ini untuk mengamankan data rahasiamu).
4. Setelah selesai mengubah, simpan file dengan menekan **Ctrl + O** (huruf O, bukan angka nol), lalu tekan **Enter**.
5. Keluar dari editor dengan menekan **Ctrl + X**.

## Langkah 7: Menyimpan Kredensial (Akun Freelance) dengan Aman

AI Agent butuh akun untuk masuk ke platform freelance. Kita akan menyimpannya dengan aman.
Ketik perintah ini di terminal (ganti email dan password dengan milikmu), lalu tekan Enter:

```bash
python3 -c "
from identity_manager import IdentityManager
m = IdentityManager()
m.save_credential('upwork', 'email@kamu.com', 'password_upwork')
m.save_credential('fiverr', 'email@kamu.com', 'password_fiverr')
print('Vault berhasil diisi!')
"
```

## Langkah 8: Menjalankan AI Agent!

Semua persiapan sudah selesai. Saatnya menghidupkan AI Agent kamu.

Ketik perintah ini dan tekan Enter:
```bash
python3 main.py
```

Selamat! AI Agent kamu sekarang sudah berjalan. Kamu bisa memantaunya dan memberinya perintah melalui bot Telegram yang sudah kamu hubungkan di Langkah 6.

### Menghentikan AI Agent
Jika kamu ingin mematikan AI Agent, kembali ke terminal Ubuntu tempat agent sedang berjalan, lalu tekan **Ctrl + C**.

### Membuka Dashboard (Opsional)
Untuk melihat dashboard statistik, buka terminal Ubuntu *baru*, masuk ke folder AI Agent lagi (`cd /path/ke/folder`), lalu ketik:
```bash
python3 dashboard.py
```
Kemudian buka browser di Windows kamu dan ketik alamat yang muncul (biasanya `http://127.0.0.1:5000`).

---

**Catatan Terakhir:** Mulai sekarang, setiap kali kamu ingin menjalankan AI Agent, kamu hanya perlu:
1. Buka aplikasi **Ubuntu** di Windows.
2. Masuk ke folder AI Agent (contoh: `cd ai-agent`).
3. Ketik `python3 main.py`.

Semoga berhasil! Jangan ragu untuk bertanya di forum atau komunitas jika ada langkah yang membingungkan.
