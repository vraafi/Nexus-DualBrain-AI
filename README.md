# Nexus DualBrain AI: Freelance AGI Lite

## Overview
Nexus DualBrain AI is a fully autonomous, lightweight agentic workflow orchestrator built to hunt for freelance Python scripting jobs, filter them based on autonomous feasibility, bid, generate code using the Gemini REST API (with 'Thinking Mode' enabled), test the code locally, and deliver the final product to the client natively via platforms like Upwork.

## "DualBrain" Architecture
The "DualBrain" concept refers to the strict separation of reasoning and execution to safely operate within constrained hardware environments (i3 Gen 8, 8GB RAM):
1. **OmniSynthesizer (Reasoning Brain):** Powered by external Gemini 4 31B via REST API with `thinkingLevel=high`. It handles language parsing, job filtering, strategy formulation, and Python code generation.
2. **Local Executor (Execution Brain):** A lightweight `subprocess` running within an isolated `virtualenv`. It tests the untrusted LLM-generated code locally to prevent system crashes. It explicitly avoids Docker to prevent Out-of-Memory (OOM) failures on 8GB RAM systems.

## Hardware Management & Stealth
- **Strict Single Execution:** Ensures only one heavy Playwright tab is open at a time.
- **Resource Limiter:** Includes `wait_for_resources` monitoring. If RAM exceeds 85% or CPU exceeds 90%, it pauses execution.
- **Stealth Browsing:** Utilizes `playwright-stealth` and persistent profiles to evade bot detection.

## Quick Start
1. Ensure Python 3.12+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Create a `.env` file at the root:
   ```env
   GEMINI_KEY_1=your_api_key
   GEMINI_KEY_2=your_backup_api_key
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   VAULT_PASSWORD=your_secure_vault_password
   ```
4. Run the orchestrator loop:
   ```bash
   python main.py
   ```
5. View progress via the CLI Dashboard:
   ```bash
   python dashboard.py
   ```
