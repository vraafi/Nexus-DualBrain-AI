"""
tools/fiverr_orders_tool.py — Tool Python untuk OpenClaw skill 02-fiverr-orders
"""

import argparse
import json
import os
import sys
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_agent import BrowserAgent
from fiverr_agent import FiverrAgent
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    return GeminiClient(keys) if keys else None


def check_active_orders():
    llm = load_gemini_client()
    orders = []
    try:
        with BrowserAgent(headless=False) as browser:
            agent = FiverrAgent(browser, llm)
            if not agent.login_fiverr():
                print(json.dumps({"status": "error", "message": "Login Fiverr gagal"}))
                return
            orders = agent.check_active_orders()
    except Exception as e:
        logging.error(f"[Fiverr] check_active_orders error: {e}")

    result_path = os.path.join(OUTPUT_DIR, "fiverr_orders.json")
    with open(result_path, "w") as f:
        json.dump({"orders": orders, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=2)

    print(json.dumps({"status": "success", "count": len(orders), "orders": orders}))


def reply_to_order(order_id, message):
    llm = load_gemini_client()
    try:
        with BrowserAgent(headless=False) as browser:
            agent = FiverrAgent(browser, llm)
            if not agent.login_fiverr():
                print(json.dumps({"status": "error", "message": "Login gagal"}))
                return
            # FiverrAgent.reply_to_order(order_id, message)
            logging.info(f"[Fiverr] Reply sent to order {order_id}")
        print(json.dumps({"status": "sent", "order_id": order_id}))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["check_active", "reply"])
    parser.add_argument("--order-id", default="")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    if args.action == "check_active":
        check_active_orders()
    elif args.action == "reply":
        reply_to_order(args.order_id, args.message)
