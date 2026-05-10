"""
tools/codegen_tool.py — Tool Python untuk OpenClaw skill 05-codegen
Dipanggil oleh OpenClaw via exec tool dari SKILL.md
"""

import argparse
import json
import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api_client import GeminiClient
from llm_config import CODEGEN_MODEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_gemini_client():
    keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
            if os.environ.get(f"GEMINI_KEY_{i}")]
    if not keys:
        raise ValueError("Tidak ada GEMINI_KEY_* di environment.")
    return GeminiClient(keys)


def generate_code(job_id, title, description, platform, retry=False, feedback=""):
    llm = load_gemini_client()

    extra = f"\nFeedback dari percobaan sebelumnya:\n{feedback}" if feedback else ""
    prompt = (
        f"Act as a senior Python developer. You have accepted this freelance job:\n"
        f"Platform: {platform}\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"{extra}\n\n"
        "Requirements:\n"
        "1. Write complete, production-ready Python 3.10+ code\n"
        "2. Include robust error handling (try/except on all I/O and network ops)\n"
        "3. Use logging module (not print)\n"
        "4. Write at least 3 unit tests using unittest at the bottom\n"
        "5. Add docstrings on all main functions\n"
        "6. Use only standard library + requests, beautifulsoup4, or commonly available libs\n"
        "7. The code must be fully self-contained and runnable\n\n"
        "Output ONLY valid Python code. No markdown, no explanation."
    )

    logging.info(f"[CodeGen] Generating code for job {job_id} using {CODEGEN_MODEL}...")
    code = llm.generate_content(prompt, allow_search=True, use_codegen_model=True)

    if not code:
        logging.error("[CodeGen] LLM returned empty response.")
        return False

    # Strip markdown
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0].strip()
    elif "```" in code:
        code = code.split("```")[1].strip()

    # Customer repository integration using Jules CLI and Github CLI
    # Generate repository name: py001 [c001] py
    import subprocess


    repo_name = f"py{job_id[-3:] if len(job_id) >= 3 else '001'} [c{job_id[:3] if len(job_id) >= 3 else '001'}] py"
    # GitHub repository names cannot have spaces or brackets. Sanitize it for GH but keep display name.
    gh_repo_name = repo_name.replace(" ", "-").replace("[", "").replace("]", "")
    repo_path = os.path.join(OUTPUT_DIR, repo_name)

    # Ensure the target directory exists and is empty
    if not os.path.exists(repo_path):
        os.makedirs(repo_path, exist_ok=True)

    # Create the repository folder using jules cli
    try:
        subprocess.run(["jules", "repo", "create", repo_path], check=True)
    except Exception as e:
        logging.warning(f"Jules CLI failed: {e}. Proceeding with standard directory.")

    code_path = os.path.join(repo_path, f"{job_id}_code.py")
    with open(code_path, "w") as f:
        f.write(code)

    meta = {
        "job_id": job_id,
        "title": title,
        "platform": platform,
        "model": CODEGEN_MODEL,
        "code_path": code_path,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "CODE_READY"
    }
    meta_path = os.path.join(repo_path, f"{job_id}_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logging.info(f"[CodeGen] Code saved to {code_path}")
    try:
        # Initialize a new git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        # Try github cli to create the repository and push
        subprocess.run(["gh", "repo", "create", gh_repo_name, "--private", "--source", ".", "--remote", "origin"],
                       cwd=repo_path, check=True)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
        subprocess.run(["git", "push", "-u", "origin", "HEAD"], cwd=repo_path, check=True)
    except Exception as e:
        logging.warning(f"GitHub CLI / Git failed: {e}.")

    print(json.dumps({"status": "success", "code_path": code_path, "meta_path": meta_path}))
    return True


def generate_apology(job_id, platform):
    llm = load_gemini_client()
    prompt = (
        f"Write a professional, sincere apology message to a client on {platform}.\n"
        "The situation: we could not complete the coding task after multiple attempts.\n"
        "The message should:\n"
        "- Sincerely apologize\n"
        "- Briefly explain that technical issues prevented completion\n"
        "- Offer a full refund or cancellation\n"
        "- Keep it under 100 words\n"
        "- Sound human, not robotic\n"
        "Output only the message text."
    )
    apology = llm.generate_content(prompt)
    if apology:
        apology_path = os.path.join(OUTPUT_DIR, f"{job_id}_apology.txt")
        with open(apology_path, "w") as f:
            f.write(apology.strip())
        print(json.dumps({"status": "success", "apology_path": apology_path}))
    else:
        print(json.dumps({"status": "error", "message": "Failed to generate apology"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--platform", default="upwork")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--feedback", default="")
    parser.add_argument("--action", default="generate", choices=["generate", "generate_apology"])
    args = parser.parse_args()

    if args.action == "generate_apology":
        generate_apology(args.job_id, args.platform)
    else:
        ok = generate_code(
            job_id=args.job_id,
            title=args.title,
            description=args.description,
            platform=args.platform,
            retry=args.retry,
            feedback=args.feedback
        )
        sys.exit(0 if ok else 1)
