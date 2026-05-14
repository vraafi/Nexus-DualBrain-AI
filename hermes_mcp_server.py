import os
import json
import subprocess
from mcp.server.fastmcp import FastMCP

# Inisialisasi MCP Server untuk Hermes Agent
mcp = FastMCP("HermesAgent")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

@mcp.tool()
def get_active_jobs() -> str:
    """Mendapatkan daftar pekerjaan freelance (job queue) yang berstatus ACCEPTED dan butuh penulisan kode."""
    queue_path = os.path.join(OUTPUT_DIR, "job_queue.json")
    if not os.path.exists(queue_path):
        return json.dumps({"status": "empty", "message": "Tidak ada job di queue."})
    
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            jobs = json.load(f)
            # Filter hanya job yang belum di-deliver
            active = [j for j in jobs if j.get("status") not in ["DELIVERED", "PAID", "CANCELLED"]]
            return json.dumps(active, indent=2)
    except Exception as e:
        return f"Error membaca job queue: {e}"

@mcp.tool()
def ask_client_question(platform: str, client_username: str, question: str) -> str:
    """Menginstruksikan Hermes untuk menanyakan pertanyaan klarifikasi (NEED_INFO) kepada klien."""
    q_path = os.path.join(OUTPUT_DIR, "pending_questions.json")
    qs = []
    if os.path.exists(q_path):
        try:
            with open(q_path, "r", encoding="utf-8") as f:
                qs = json.load(f)
        except:
            pass
            
    qs.append({
        "platform": platform,
        "client_username": client_username,
        "question": question,
        "status": "pending_send"
    })
    
    with open(q_path, "w", encoding="utf-8") as f:
        json.dump(qs, f, indent=4)
        
    return f"Pertanyaan berhasil diantrekan. Hermes akan segera meneruskannya ke {client_username} di {platform}."

@mcp.tool()
def submit_code_for_testing(task_id: str, code_path: str) -> str:
    """Menyerahkan kode yang sudah selesai dibuat oleh Antigravity kepada Hermes untuk diuji di Sandbox (bwrap)."""
    status_path = os.path.join(OUTPUT_DIR, "code_submissions.json")
    subs = []
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                subs = json.load(f)
        except:
            pass
            
    subs.append({
        "task_id": task_id,
        "code_path": code_path,
        "status": "ready_for_sandbox"
    })
    
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(subs, f, indent=4)
        
    return f"Kode {code_path} untuk task {task_id} berhasil diserahkan! Hermes akan segera melakukan Sandbox Testing."

@mcp.tool()
def request_hermes_to_test_code(code_path: str) -> str:
    """
    Meminta Hermes Agent untuk mengeksekusi/menguji kode yang baru dibuat di terminal secara langsung.
    Jika kode error, Hermes akan mengembalikan log error terminal agar Antigravity bisa memperbaiki.
    Jika kode sukses, Hermes akan mengembalikan log sukses agar Antigravity bisa upgrade atau bilang selesai.
    """
    if not os.path.exists(code_path):
        return f"Error: File {code_path} tidak ditemukan!"
    
    try:
        # Eksekusi sederhana via subprocess untuk mendapatkan log terminal
        result = subprocess.run(
            ["python", code_path], 
            capture_output=True, 
            text=True, 
            timeout=120
        )
        
        output = f"--- STDOUT ---\n{result.stdout}\n"
        output += f"--- STDERR ---\n{result.stderr}\n"
        output += f"--- EXIT CODE: {result.returncode} ---\n"
        
        if result.returncode != 0:
            return f"[ERROR DETECTED]\nTerminal Log:\n{output}\n\nSilakan perbaiki error di atas dan panggil tool ini lagi untuk mengeceknya."
        else:
            return f"[SUCCESS]\nTerminal Log:\n{output}\n\nKode berhasil dijalankan tanpa error! Silakan nyatakan selesai atau upgrade kodenya jika dirasa kurang sempurna."
            
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]\nKode berjalan terlalu lama (lebih dari 120 detik) dan dihentikan otomatis. Periksa apakah ada infinite loop."
    except Exception as e:
        return f"[SYSTEM ERROR]\nGagal menjalankan terminal test: {e}"

if __name__ == "__main__":
    # Menjalankan server MCP melalui standard input/output (stdio)
    mcp.run()
