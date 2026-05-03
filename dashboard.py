import sqlite3
import time
import os
import psutil

DB_NAME = "agent_state.db"

def print_header():
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*60)
    print(" "*15 + "AGI-LITE COMMAND CENTER")
    print("="*60)

def display_hardware_stats():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent()
    print(f"[HARDWARE] CPU: {cpu}% | RAM: {ram.percent}% ({ram.used/(1024**3):.1f}GB/{ram.total/(1024**3):.1f}GB)")
    print("-" * 60)

def display_active_tasks():
    print("[ACTIVE TASKS]")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, status, current_step FROM task_state ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        if not rows:
            print("  No active tasks.")
        for row in rows:
            print(f"  [{row[1]}] {row[0][:8]}... -> {row[2]}")
        conn.close()
    except Exception as e:
        print(f"  Error reading database: {e}")
    print("-" * 60)

def main():
    try:
        while True:
            print_header()
            display_hardware_stats()
            display_active_tasks()
            print("\nPress Ctrl+C to exit dashboard.")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nExiting dashboard.")

if __name__ == "__main__":
    main()
