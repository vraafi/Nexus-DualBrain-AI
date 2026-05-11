"""
tools/freelancer_search_tool.py — Tool Python untuk OpenClaw skill 03-freelancer-search
"""

import json
import os
import sys
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from freelancer_agent import FreelancerAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    return GeminiClient(keys) if keys else None


def search_jobs():
    llm = load_gemini_client()
    jobs = []
    try:
        with BrowserAgent(headless=False) as browser:
            agent = FreelancerAgent(browser, llm)
            if not agent.login_freelancer():
                print(json.dumps({"status": "error", "message": "Login Freelancer gagal"}))
                return
            jobs = agent.check_job_matches()
    except Exception as e:
        logging.error(f"[Freelancer] search error: {e}")

    output_path = os.path.join(OUTPUT_DIR, "freelancer_jobs.json")
    with open(output_path, "w") as f:
        json.dump({"jobs": jobs, "searched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=2)

    print(json.dumps({"status": "success", "count": len(jobs), "output_path": output_path}))


if __name__ == "__main__":
    search_jobs()
