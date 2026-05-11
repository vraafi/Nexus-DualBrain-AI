"""
tools/freelancer_apply_tool.py — Submit bid ke Freelancer.com
"""
import argparse
import json
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from freelancer_agent import FreelancerAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    return GeminiClient(keys) if keys else None


def submit_bid(job_id, bid_amount, proposal):
    llm = load_gemini_client()
    try:
        with BrowserAgent(headless=False) as browser:
            agent = FreelancerAgent(browser, llm)
            if not agent.login_freelancer():
                print(json.dumps({"status": "error", "message": "Login gagal"}))
                return
            result = agent.apply_to_job(
                {"job_id": job_id, "budget": bid_amount}, proposal
            ) if hasattr(agent, "apply_to_job") else False
            if result:
                print(json.dumps({"status": "bid_sent", "job_id": job_id, "amount": bid_amount}))
            else:
                print(json.dumps({"status": "failed", "job_id": job_id}))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--bid-amount", type=float, required=True)
    parser.add_argument("--proposal", required=True)
    args = parser.parse_args()
    submit_bid(args.job_id, args.bid_amount, args.proposal)
