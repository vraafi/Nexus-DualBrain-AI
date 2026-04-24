import time
import sys
import gc
import json
from datetime import datetime

from module1_research import run_research
from module2_video_gen import run_video_generation
from telegram_sender import send_videos_to_telegram
import state_manager

def generate_completion_report(state):
    """
    Menulis Completion Report terstruktur untuk menghindari context drift.
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "final_state": state,
        "reasoning": "Workflow berhasil mencapai Modul 3 dan mengonfirmasi pengiriman Telegram sukses.",
        "status": "COMPLETED"
    }
    with open("completion_report.log", "a") as f:
        f.write(json.dumps(report) + "\n")
    print("\n--- Completion Report Tersimpan ---")

def main():
    """
    Arsitektur kode HARUS sekuensial (bergantian murni).
    Dilengkapi State Machine untuk auto-resume dan pembersihan RAM eksplisit.
    """
    print("="*50)
    print("Memulai Agentic Workflow secara Sekuensial (Otonom)")
    print("="*50)

    state_manager.init_db()
    state = state_manager.get_state()

    if state and state.get("status") == "completed":
        print("Siklus sebelumnya sudah selesai. Mereset state untuk siklus baru...")
        state_manager.reset_state()
        state = state_manager.get_state()

    current_module = state.get("current_module", 1)
    product_data = state.get("product_data", {})
    video_paths = state.get("video_paths", [])

    print(f"Resume State: Berada di Modul {current_module}")

    # ---------------------------------------------------------
    # Modul 1: Riset Analitik (TikTok Creative Center)
    # ---------------------------------------------------------
    if current_module <= 1:
        print("\n>>> Memulai Eksekusi Modul 1: Riset Analitik...")
        time.sleep(2)

        product_data = run_research()
        if not product_data:
            print("Modul 1 gagal. Menghentikan workflow untuk retry siklus berikutnya.")
            sys.exit(1)

        print(f"Hasil Modul 1: {product_data}")
        state_manager.update_state(current_module=2, product_data=product_data)

        print("\nJeda istirahat 5 detik untuk mengosongkan RAM...")
        time.sleep(5)

    # ---------------------------------------------------------
    # Modul 2: Generasi Video Rotasi & Manajemen Prompt
    # ---------------------------------------------------------
    if current_module <= 2:
        print("\n>>> Memulai Eksekusi Modul 2: Generasi Video...")
        video_paths = run_video_generation(product_data)

        if not video_paths:
            print("Modul 2 gagal. Menghentikan workflow untuk retry siklus berikutnya.")
            sys.exit(1)

        print(f"Hasil Modul 2 (Path Video): {video_paths}")
        state_manager.update_state(current_module=3, video_paths=video_paths)

        print("\nJeda istirahat 5 detik untuk sistem I/O...")
        time.sleep(5)

    # ---------------------------------------------------------
    # Modul 3: Pengiriman ke Telegram
    # ---------------------------------------------------------
    if current_module <= 3:
        print("\n>>> Memulai Eksekusi Modul 3: Pengiriman ke Telegram...")
        success = send_videos_to_telegram(video_paths)

        if success:
            state_manager.update_state(current_module=4, status="completed")
            final_state = state_manager.get_state()
            generate_completion_report(final_state)
            print("\nWorkflow berhasil diselesaikan sepenuhnya.")
        else:
            print("\nWorkflow selesai dengan error pada pengiriman Telegram. State tidak di-complete agar bisa di-resume.")
            sys.exit(1)

    # ---------------------------------------------------------
    # Exit Criteria & Explicit Garbage Collection
    # ---------------------------------------------------------
    print("\nMelakukan pembersihan RAM eksplisit (Exit Criteria)...")
    try:
        del product_data
        del video_paths
        del state
    except:
        pass
    gc.collect()
    print("Memori RAM dibilas. Agen siap untuk hibernasi atau siklus selanjutnya.")

if __name__ == "__main__":
    main()
