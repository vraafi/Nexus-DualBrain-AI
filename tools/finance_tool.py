"""
tools/finance_tool.py — Tool Python untuk OpenClaw skill keuangan
Dipanggil oleh OpenClaw via exec tool
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from financial_tracker import FinancialTracker


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True,
                        choices=["log_proposal", "update_status", "summary", "recent"])
    parser.add_argument("--platform", default="upwork")
    parser.add_argument("--title", default="")
    parser.add_argument("--budget", type=float, default=0.0)
    parser.add_argument("--status", default="DELIVERED")
    parser.add_argument("--revenue", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    ft = FinancialTracker()

    if args.action == "log_proposal":
        ft.log_proposal(args.platform, args.title, args.budget)
        print(json.dumps({"status": "logged", "platform": args.platform, "title": args.title}))

    elif args.action == "update_status":
        ft.update_job_status(args.title, args.status, args.revenue)
        print(json.dumps({"status": "updated", "title": args.title, "new_status": args.status}))

    elif args.action == "summary":
        summary = ft.get_summary()
        print(json.dumps(summary))

    elif args.action == "recent":
        jobs = ft.get_recent_jobs(args.limit)
        print(json.dumps(jobs))
