"""
tools/delivery_tool.py — Tool Python untuk OpenClaw skill 07-deliver
Kirim hasil kerja ke klien di platform yang sesuai
"""

import argparse
import json
import os
import sys
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
QUEUE_PATH = os.path.join(OUTPUT_DIR, "job_queue.json")


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    if not keys:
        raise ValueError("Tidak ada GEMINI_KEY_* di environment.")
    return GeminiClient(keys)


def load_queue():
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return []


def save_queue(queue):
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2)


def deliver_work(platform, job_id, order_id, code_path, message, retry=False):
    """Kirim hasil kerja ke platform."""
    if not os.path.exists(code_path):
        print(json.dumps({"status": "error", "message": f"File tidak ditemukan: {code_path}"}))
        return False

    try:
        with BrowserAgent(headless=False, endpoint_url="http://localhost:9222") as browser:
            llm = load_gemini_client()
            delivered = False

            if platform == "upwork":
                from freelance_agent import FreelanceAgent
                agent = FreelanceAgent(browser, llm)
                job_data = {"title": job_id, "platform": "upwork", "order_id": order_id}
                delivered = agent.deliver_work(job_data, code_path)

            elif platform == "fiverr":
                from fiverr_agent import FiverrAgent
                agent = FiverrAgent(browser, llm)
                job_data = {"order_id": order_id, "title": job_id}
                delivered = agent.deliver_order(job_data, code_path, message)

            elif platform == "freelancer":
                from freelancer_agent import FreelancerAgent
                agent = FreelancerAgent(browser, llm)
                job_data = {"title": job_id, "platform": "freelancer", "order_id": order_id}
                delivered = agent.deliver_work(job_data, code_path)

        if delivered:
            # Update queue status
            queue = load_queue()
            for item in queue:
                if item.get("job_id") == job_id or item.get("order_id") == order_id:
                    item["status"] = "DELIVERED"
                    item["delivered_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_queue(queue)

            print(json.dumps({
                "status": "delivered",
                "platform": platform,
                "job_id": job_id,
                "order_id": order_id,
                "code_path": code_path
            }))
            return True
        else:
            print(json.dumps({"status": "failed", "message": "Delivery gagal di platform"}))
            return False

    except Exception as e:
        logging.error(f"[Delivery] Error: {e}")
        print(json.dumps({"status": "error", "message": str(e)}))
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["upwork", "fiverr", "freelancer"])
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--order-id", default="")
    parser.add_argument("--code-path", required=True)
    parser.add_argument("--message", default="Please find the completed work attached.")
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()

    ok = deliver_work(
        platform=args.platform,
        job_id=args.job_id,
        order_id=args.order_id,
        code_path=args.code_path,
        message=args.message,
        retry=args.retry
    )
    sys.exit(0 if ok else 1)
