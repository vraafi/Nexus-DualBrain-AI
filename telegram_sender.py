import requests
import os

# Harap ganti dengan kredensial yang sesungguhnya di production
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

def send_videos_to_telegram(video_paths):
    """
    Modul 3: Pengiriman ke Telegram
    Menggunakan Python library requests endpoint /sendDocument (mode multipart/form-data).
    File video dikirim sebagai file agar tidak dikompresi.
    Menghapus file lokal apabila HTTP 200 OK diterima.
    """
    if not video_paths:
        print("Tidak ada video yang diterima untuk dikirim ke Telegram.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    all_success = True

    for path in video_paths:
        if not os.path.exists(path):
            print(f"File tidak ditemukan: {path}")
            all_success = False
            continue

        print(f"Mengirim file {path} ke Telegram (chat id: {TELEGRAM_CHAT_ID})...")

        try:
            with open(path, 'rb') as video_file:
                # payload 'document' akan diproses sebagai multipart/form-data oleh requests
                files = {'document': video_file}
                data = {'chat_id': TELEGRAM_CHAT_ID}

                response = requests.post(url, data=data, files=files, timeout=60)

            if response.status_code == 200:
                print(f"File {path} berhasil dikirim (HTTP 200 OK).")
                # Hapus file video lokal dari hardisk
                try:
                    os.remove(path)
                    print(f"File lokal {path} telah dihapus untuk menghemat ruang penyimpanan.")
                except Exception as e_remove:
                    print(f"Gagal menghapus file lokal {path}: {e_remove}")
            else:
                print(f"Gagal mengirim file {path}. Status code: {response.status_code}, Response: {response.text}")
                all_success = False

        except requests.exceptions.RequestException as e:
            print(f"Error pada saat mengirim data ke Telegram: {e}")
            all_success = False

    return all_success

if __name__ == "__main__":
    # Test stub
    pass
