"""
tools/upwork_search_tool.py — Tool Python untuk OpenClaw skill 01-upwork-search
Cari dan apply job di Upwork menggunakan BrowserAgent
"""

import json
import os
import sys
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from freelance_agent import FreelanceAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Kriteria filter job
MIN_BUDGET_FIXED = 30
MIN_RATE_HOURLY = 15
ALLOWED_KEYWORDS = [
    "python", "script", "automation", "scraping", "web scraper",
    "data processing", "bot", "api integration", "backend", "parsing"
]
MAX_PROPOSALS_PER_SESSION = 10


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    if not keys:
        raise ValueError("Tidak ada GEMINI_KEY_* di environment.")
    return GeminiClient(keys)


def filter_job(job: dict, llm) -> tuple[bool, str]:
    """Filter job berdasarkan kriteria. Return (passed, reason)."""
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    budget = float(job.get("budget") or job.get("rate") or 0)
    job_type = job.get("job_type", "fixed").lower()

    # Keyword check
    combined = title + " " + description
    if not any(kw in combined for kw in ALLOWED_KEYWORDS):
        return False, "Tidak ada keyword Python/coding yang cocok"

    # Budget check
    if job_type == "hourly" and budget < MIN_RATE_HOURLY:
        return False, f"Rate terlalu rendah: ${budget}/hr (min ${MIN_RATE_HOURLY})"
    if job_type == "fixed" and budget < MIN_BUDGET_FIXED:
        return False, f"Budget terlalu rendah: ${budget} (min ${MIN_BUDGET_FIXED})"

    # Feasibility check via LLM (cepat, pakai flash model)
    feasibility_prompt = (
        f"Job title: {job.get('title')}\n"
        f"Description: {description[:500]}\n\n"
        "Can this job be completed 100% autonomously by an AI coding agent "
        "without physical hardware, personal accounts, or sensitive NDA access? "
        "Answer only YES or NO."
    )
    answer = llm.generate_content(feasibility_prompt)
    if answer and "YES" not in answer.upper():
        return False, "LLM: Job tidak feasible untuk AI otonom"

    return True, "OK"


def search_and_filter_jobs():
    llm = load_gemini_client()
    all_jobs = []
    filtered_jobs = []

    try:
        with BrowserAgent(headless=True) as browser:
            agent = FreelanceAgent(browser, llm)

            # Login Upwork
            if not agent.login_upwork():
                print(json.dumps({"status": "error", "message": "Login Upwork gagal"}))
                return

            # Cari job
            raw_jobs = agent.search_jobs() if hasattr(agent, "search_jobs") else []
            all_jobs = raw_jobs

    except Exception as e:
        logging.error(f"[UpworkSearch] Browser error: {e}")
        all_jobs = []

    # Filter jobs
    for job in all_jobs:
        passed, reason = filter_job(job, llm)
        job["filter_passed"] = passed
        job["filter_reason"] = reason
        if passed:
            filtered_jobs.append(job)
        logging.info(f"[Filter] {job.get('title', 'N/A')[:50]}: {reason}")

    output = {
        "total_found": len(all_jobs),
        "total_filtered": len(filtered_jobs),
        "jobs": filtered_jobs,
        "searched_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    output_path = os.path.join(OUTPUT_DIR, "upwork_jobs.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(json.dumps({
        "status": "success",
        "total_found": len(all_jobs),
        "total_filtered": len(filtered_jobs),
        "output_path": output_path
    }))


if __name__ == "__main__":
    search_and_filter_jobs()
