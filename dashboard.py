import sqlite3
import time
import os
import psutil
from datetime import datetime

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_latest_log():
    try:
        with open("agent_orchestrator.log", "r") as f:
            lines = f.readlines()
            # Get the last 5 logs, stripping newlines
            return [line.strip() for line in lines[-5:]]
    except Exception:
        return ["Log file not found or empty."]

def get_db_stats():
    try:
        conn = sqlite3.connect("agent_state.db")
        cursor = conn.cursor()

        # Get active tasks
        cursor.execute("SELECT task_name, status, last_updated FROM task_state WHERE status='IN_PROGRESS'")
        active = cursor.fetchall()

        # Get financial total
        cursor.execute("SELECT SUM(amount) FROM financial_records")
        total_money = cursor.fetchone()[0] or 0.0

        conn.close()
        return active, total_money
    except Exception as e:
        return [], 0.0

def main():
    while True:
        clear_screen()
        print("="*60)
        print("    NEXUS DUAL-BRAIN AGI - LIVE COMMAND CENTER")
        print("="*60)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Hardware Status
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent()
        disk = psutil.disk_usage('/').percent
        print("\n[ HARDWARE STATUS ]")
        print(f"RAM: {ram}% | CPU: {cpu}% | SSD: {disk}%")
        if ram > 80:
            print("WARNING: RAM is running high! AGI might trigger gc.collect() soon.")

        # Financial Status
        active_tasks, total_money = get_db_stats()
        print(f"\n[ FINANCIAL STATUS ]")
        print(f"Estimated Autonomous Value Generated: ${total_money:.2f}")

        # Current Thoughts/Tasks
        print("\n[ ACTIVE AGI TASKS ]")
        if not active_tasks:
            print("No active tasks. AGI might be sleeping (cooling down) or starting up.")
        for task in active_tasks:
            print(f"- {task[0]} [Status: {task[1]}] (Last updated: {task[2]})")

        # Live Brain Log (What is it doing exactly right now)
        print("\n[ LIVE AGI BRAIN LOGS ]")
        logs = get_latest_log()
        for log in logs:
            print(log)

        print("\n" + "="*60)
        print("Press Ctrl+C to exit dashboard. (AGI will continue running in background)")

        time.sleep(2) # Refresh every 2 seconds

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting dashboard...")
