import time
import sys

from module1_research import run_research
from module2_video_gen import run_video_generation
from telegram_sender import send_videos_to_telegram

def main():
    """
    Arsitektur kode HARUS sekuensial (bergantian murni).
    Dilarang keras menulis kode yang mengeksekusi tugas secara paralel,
    multiprocessing, atau membuka lebih dari 1 tab browser berat pada waktu yang sama.
    """
    print("="*50)
    print("Memulai Agentic Workflow secara Sekuensial")
    print("="*50)

    # ---------------------------------------------------------
    # Modul 1: Riset Analitik (TikTok Creative Center)
    # ---------------------------------------------------------
    print("\n>>> Memulai Eksekusi Modul 1: Riset Analitik...")
    # Menunggu sedikit jeda memori untuk stabilitas pada mesin i3 RAM 8GB
    time.sleep(2)

    product_data = run_research()
    if not product_data:
        print("Modul 1 gagal mendapatkan data produk. Menghentikan workflow.")
        sys.exit(1)

    print(f"Hasil Modul 1: {product_data}")

    # Jeda wajib agar RAM sepenuhnya dibilas setelah driver.quit() di modul 1
    print("\nJeda istirahat 5 detik untuk mengosongkan RAM...")
    time.sleep(5)

    # ---------------------------------------------------------
    # Modul 2: Generasi Video Rotasi & Manajemen Prompt
    # ---------------------------------------------------------
    print("\n>>> Memulai Eksekusi Modul 2: Generasi Video...")
    video_paths = run_video_generation(product_data)

    if not video_paths:
        print("Modul 2 gagal menghasilkan video. Menghentikan workflow.")
        sys.exit(1)

    print(f"Hasil Modul 2 (Path Video): {video_paths}")

    # Jeda wajib untuk sistem I/O
    print("\nJeda istirahat 5 detik untuk sistem I/O...")
    time.sleep(5)

    # ---------------------------------------------------------
    # Modul 3: Pengiriman ke Telegram
    # ---------------------------------------------------------
    print("\n>>> Memulai Eksekusi Modul 3: Pengiriman ke Telegram...")
    success = send_videos_to_telegram(video_paths)

    if success:
        print("\nWorkflow berhasil diselesaikan sepenuhnya.")
    else:
        print("\nWorkflow selesai dengan beberapa error pada pengiriman Telegram.")
        sys.exit(1)

if __name__ == "__main__":
    main()
