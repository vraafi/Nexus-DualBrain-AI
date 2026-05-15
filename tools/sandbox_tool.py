"""
tools/sandbox_tool.py — Tool Python untuk Hermes Agent skill 06-sandbox-test
Eksekusi kode di bwrap sandbox dengan self-correction loop
"""

import argparse
import json
import os
import sys
import subprocess
import time
import logging
import shutil
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api_client import GeminiClient
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

SANDBOX_ENV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox_env")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "sandbox_results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    if not keys:
        raise ValueError("Tidak ada GEMINI_KEY_* di environment.")
    return GeminiClient(keys)


def setup_sandbox_env():
    if not os.path.exists(SANDBOX_ENV):
        logging.info("Setup sandbox virtualenv...")
        subprocess.run(["python3", "-m", "venv", SANDBOX_ENV], check=True)
        pip = os.path.join(SANDBOX_ENV, "bin", "pip")
        subprocess.run([pip, "install", "requests", "beautifulsoup4", "flake8", "pytest"],
                       check=True, capture_output=True)
    return os.path.join(SANDBOX_ENV, "bin", "python")


def static_analysis(code_path):
    flake8 = os.path.join(SANDBOX_ENV, "bin", "flake8")
    try:
        result = subprocess.run([flake8, code_path, "--max-line-length=120"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stdout
        return True, ""
    except Exception as e:
        return True, ""  # Jangan blokir jika flake8 tidak bisa jalan


def search_error(error_msg):
    try:
        query = error_msg[:200].strip()
        results = DDGS().text(f"Python error fix: {query}", max_results=3)
        return "\n".join([r.get("body", "") for r in results])
    except Exception:
        return ""


from llm_sandbox import SandboxSession

def run_in_bwrap(python_exe, code_path, timeout_seconds=900):
    """Eksekusi kode di bwrap sandbox yang terisolasi."""
    try:
        with SandboxSession(lang="python", keep_template=True) as session:
            remote_path = f"/workspace/script.py"
            session.copy(code_path, remote_path)

            result = session.execute(f"python {remote_path}")

            if result.is_success:
                return True, result.text, ""
            else:
                return False, "", result.text

    except Exception as e:
        if 'Timeout' in str(type(e)):
            return False, "", "TIMEOUT: Eksekusi melebihi batas waktu."
        return False, "", str(e)


def fix_code(llm, code, error_output, search_context=""):
    prompt = (
        "You are a Python debugging expert. Fix the following Python code.\n\n"
        f"ERROR OUTPUT:\n{error_output[:1000]}\n\n"
        f"WEB SEARCH CONTEXT:\n{search_context[:500]}\n\n"
        f"ORIGINAL CODE:\n{code}\n\n"
        "Return ONLY the fixed Python code. No explanation, no markdown."
    )
    fixed = llm.generate_content(prompt)
    if fixed:
        if "```python" in fixed:
            fixed = fixed.split("```python")[1].split("```")[0].strip()
        elif "```" in fixed:
            fixed = fixed.split("```")[1].strip()
    return fixed


def test_code(job_id, code_path, max_attempts=7, timeout_minutes=15):
    python_exe = setup_sandbox_env()
    llm = load_gemini_client()
    timeout_seconds = timeout_minutes * 60
    result_path = os.path.join(RESULTS_DIR, f"{job_id}_result.json")
    generated_dir = os.path.dirname(code_path)
    final_path = os.path.join(generated_dir, f"{job_id}_final.py")

    with open(code_path, "r") as f:
        current_code = f.read()

    start_time = time.time()

    for attempt in range(1, max_attempts + 1):
        if time.time() - start_time > 30 * 60:
            logging.error("Total sandbox time exceeded 30 minutes.")
            break

        logging.info(f"[Sandbox] Attempt {attempt}/{max_attempts} for job {job_id}")

        # Write current code to temp file
        tmp_path = f"/tmp/sandbox_test_{job_id}_{attempt}.py"
        with open(tmp_path, "w") as f:
            f.write(current_code)

        # Static analysis
        ok, flake_output = static_analysis(tmp_path)
        if not ok:
            logging.warning(f"[Sandbox] Static analysis issues: {flake_output[:200]}")
            search_ctx = search_error(flake_output)
            current_code = fix_code(llm, current_code, flake_output, search_ctx) or current_code
            os.unlink(tmp_path)
            continue

        # Execute in bwrap
        success, stdout, stderr = run_in_bwrap(python_exe, tmp_path, timeout_seconds)
        os.unlink(tmp_path)

        if success:
            logging.info(f"[Sandbox] PASSED on attempt {attempt}")
            with open(final_path, "w") as f:
                f.write(current_code)
            result = {
                "job_id": job_id, "status": "PASSED", "attempts": attempt,
                "final_code_path": final_path,
                "stdout": stdout[:500], "passed_at": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)
            print(json.dumps(result))
            return True

        # Fix code
        error_info = stderr or stdout
        logging.warning(f"[Sandbox] Attempt {attempt} failed: {error_info[:200]}")
        search_ctx = search_error(error_info)
        fixed = fix_code(llm, current_code, error_info, search_ctx)
        if fixed:
            current_code = fixed

        time.sleep(2)

    # All attempts failed
    result = {
        "job_id": job_id, "status": "FAILED", "attempts": max_attempts,
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result))
    return False


def cleanup(job_id):
    tmp_files = [f for f in os.listdir("/tmp") if f.startswith(f"sandbox_test_{job_id}")]
    for f in tmp_files:
        try:
            os.unlink(os.path.join("/tmp", f))
        except Exception:
            pass
    print(json.dumps({"status": "cleaned", "job_id": job_id}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-path", default="")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--max-attempts", type=int, default=7)
    parser.add_argument("--timeout-minutes", type=int, default=15)
    parser.add_argument("--action", default="test", choices=["test", "cleanup"])
    args = parser.parse_args()

    if args.action == "cleanup":
        cleanup(args.job_id)
    else:
        ok = test_code(
            job_id=args.job_id,
            code_path=args.code_path,
            max_attempts=args.max_attempts,
            timeout_minutes=args.timeout_minutes
        )
        sys.exit(0 if ok else 1)
