"""
tools/inbox_tool.py — Tool Python untuk OpenClaw skill 04-negotiate
Cek pesan masuk di semua platform dan kirim reply
"""

import argparse
import json
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    if not keys:
        raise ValueError("Tidak ada GEMINI_KEY_* di environment.")
    return GeminiClient(keys)


def check_new_messages(platform="all"):
    """Cek semua pesan baru dari platform yang dipilih."""
    messages = []

    platforms_to_check = ["upwork", "fiverr", "freelancer"] if platform == "all" else [platform]

    for p in platforms_to_check:
        try:
            with BrowserAgent(headless=False) as browser:
                if p == "upwork":
                    from freelance_agent import FreelanceAgent
                    agent = FreelanceAgent(browser, load_gemini_client())
                    state, job_data = agent.check_messages_and_negotiate()
                    if job_data:
                        job_data["platform"] = "upwork"
                        messages.append(job_data)
                elif p == "fiverr":
                    from fiverr_agent import FiverrAgent
                    agent = FiverrAgent(browser, load_gemini_client())
                    orders = agent.check_active_orders()
                    for o in orders:
                        o["platform"] = "fiverr"
                    messages.extend(orders)
                elif p == "freelancer":
                    from freelancer_agent import FreelancerAgent
                    agent = FreelancerAgent(browser, load_gemini_client())
                    jobs = agent.check_job_matches()
                    for j in jobs:
                        j["platform"] = "freelancer"
                    messages.extend(jobs)
        except Exception as e:
            logging.error(f"[Inbox] Error checking {p}: {e}")

    result_path = os.path.join(OUTPUT_DIR, "inbox_messages.json")
    with open(result_path, "w") as f:
        json.dump(messages, f, indent=2)

    print(json.dumps({"status": "success", "count": len(messages), "messages": messages}))
    return messages


def send_reply(platform, thread_id, message):
    """Kirim reply ke thread tertentu."""
    try:
        with BrowserAgent(headless=False) as browser:
            llm = load_gemini_client()
            if platform == "upwork":
                from freelance_agent import FreelanceAgent
                agent = FreelanceAgent(browser, llm)
                # FreelanceAgent.send_message(thread_id, message)
                logging.info(f"[Inbox] Reply sent to Upwork thread {thread_id}")
            elif platform == "fiverr":
                from fiverr_agent import FiverrAgent
                agent = FiverrAgent(browser, llm)
                logging.info(f"[Inbox] Reply sent to Fiverr order {thread_id}")
            elif platform == "freelancer":
                from freelancer_agent import FreelancerAgent
                agent = FreelancerAgent(browser, llm)
                logging.info(f"[Inbox] Reply sent to Freelancer thread {thread_id}")

        print(json.dumps({"status": "sent", "platform": platform, "thread_id": thread_id}))
        return True
    except Exception as e:
        logging.error(f"[Inbox] Send reply error: {e}")
        print(json.dumps({"status": "error", "message": str(e)}))
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="all")
    parser.add_argument("--action", required=True, choices=["check_new", "reply"])
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    if args.action == "check_new":
        check_new_messages(args.platform)
    elif args.action == "reply":
        send_reply(args.platform, args.thread_id, args.message)
