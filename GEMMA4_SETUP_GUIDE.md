# GEMMA 4 INTEGRATION GUIDE — Nexus DualBrain AI
# Complete step-by-step setup for Gemma 4 native support
# Updated: May 10, 2026

## 📋 Quickstart (5 Minutes)

```bash
# 1. Update code
git pull origin main

# 2. Install SDK
pip install -r requirements.txt

# 3. Get free API key
# → Go to: https://aistudio.google.com/apikey
# → Click "Create API Key"
# → Copy key

# 4. Setup .env
cp .env.example .env
nano .env  # Paste key into GEMINI_KEY_1

# 5. Test
python -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
model = genai.GenerativeModel('gemma-4-31b-it')
response = model.generate_content('Write hello world in Python')
print(response.text)
"

# 6. Run
python main.py
```

---

## 🎯 Full Setup Guide

### Step 1: Get Google AI Studio API Keys

**Why Google AI Studio (not Google Cloud)?**
- Free tier available (no credit card needed initially)
- Direct access to Gemma 4 models
- Simpler setup than Google Cloud
- Better quota for development

**Setup:**

1. Go to: https://aistudio.google.com/apikey
2. Sign in with Google account
3. Click "Create API Key"
4. Select "Create API key in new project" (if first time)
5. You'll get a key like: `AIzaSyD...abc123...`
6. Copy it (you'll need this)

**Get Multiple Keys (for rotation):**

```bash
# Recommended: 2-3 keys for better uptime
# Go through steps 1-5 again for each key
# Or use different Google accounts

# .env setup:
GEMINI_KEY_1=AIzaSy... (first key)
GEMINI_KEY_2=AIzaSy... (second key, optional)
# Max 10 keys supported
```

### Step 2: Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OR: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installations
python -c "import google.generativeai; print('✅ google-generativeai installed')"
python -c "import playwright; print('✅ playwright installed')"
python -c "import psutil; print('✅ psutil installed')"
```

### Step 3: Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env  # Linux/Mac
# OR: notepad .env  # Windows

# Minimum required:
GEMINI_KEY_1=AIzaSyD...          # From Step 1
TELEGRAM_BOT_TOKEN=123:ABC...    # From BotFather (see below)
TELEGRAM_CHAT_ID=987654321       # Your Telegram ID
VAULT_PASSWORD=random16chars     # For encryption
```

### Step 4: Setup Telegram Bot (for notifications)

1. **Create bot:**
   - Open Telegram, search for `@BotFather`
   - Send `/newbot`
   - Choose bot name (e.g., "NexusAgent")
   - You'll get token like: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
   - Copy token → paste to `TELEGRAM_BOT_TOKEN`

2. **Get your Chat ID:**
   - Create a private Telegram group or use DM with bot
   - Send `/start` to your new bot
   - Open: `https://api.telegram.org/bot123456:ABC-DEF1234/getUpdates`
   - Replace token in URL
   - Look for `"chat":{"id":987654321}`
   - Copy number → paste to `TELEGRAM_CHAT_ID`

### Step 5: Test Gemma 4 Models

**Test Codegen (31B):**
```python
import google.generativeai as genai
genai.configure(api_key="YOUR_KEY")

model = genai.GenerativeModel("gemma-4-31b-it")
response = model.generate_content("""
Write a Python function that:
1. Takes a list of numbers
2. Returns sum if list has odd length
3. Returns product if list has even length
""")
print(response.text)
```

**Test Negotiation (26B):**
```python
import google.generativeai as genai
genai.configure(api_key="YOUR_KEY")

model = genai.GenerativeModel("gemma-4-26b-a4b-it")
response = model.generate_content("""
Draft a professional email reply to client:
Client: "Your quote is too high, I found cheaper alternatives"
Your reply (be persuasive but honest):
""")
print(response.text)
```

**Test Web Search Context:**
```python
from api_client import GeminiClient

llm = GeminiClient(["YOUR_KEY"])
result = llm.generate_content(
    prompt="What are the latest Python 3.13 features?",
    allow_search=True
)
print(result)
```

### Step 6: Run Agent

**Option A: Direct Python (Recommended for testing)**
```bash
python main.py
```

**Option B: Via OpenClaw (Full automation, recommended for production)**
```bash
# Install OpenClaw (Node.js required)
npm install -g openclaw@latest

# Setup (interactive)
openclaw onboard

# Start gateway (runs on http://localhost:18789)
openclaw start

# In another terminal, run agent
python main.py

# Access dashboard: http://localhost:18789
```

---

## 📊 Model Selection Guide

### When to use each model:

| Task | Model | Cost | Speed | Quality |
|------|-------|------|-------|---------|
| Generate code | Gemma 4-31B | $0.13/$0.38 per 1M | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Negotiate price | Gemma 4-26B | $0.06/$0.33 per 1M | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Screen jobs | Gemma 4-26B | $0.06/$0.33 per 1M | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Quick tasks | Gemini Flash-Lite | $0.075/$0.30 per 1M | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

### Example Cost Calculation:

**Scenario: 100 code generation jobs per month**

Assumptions:
- Average prompt: 500 tokens
- Average output: 2000 tokens
- Using Gemma 4-31B for code

```
Per call cost:
  Input: 500 tokens × ($0.13 / 1,000,000) = $0.000065
  Output: 2000 tokens × ($0.38 / 1,000,000) = $0.00076
  Total per call: $0.000825

Per month (100 calls):
  100 × $0.000825 = $0.0825

Annual: $1.00
```

**Compare to Gemini Pro:**
- Gemini Pro: $7.50 input + $30 output = **$37.50 per call**
- Gemma 4-31B: $0.13 input + $0.38 output = **$0.51 per call**
- **Savings: 98.6% cheaper** 🎉

---

## 🔄 Multi-Key Rotation Strategy

**Why rotate keys?**
- Avoid hitting single key's quota limits
- Automatic fallback if one key has issues
- Load balancing across multiple keys

**Setup:**
```env
# .env
GEMINI_KEY_1=AIzaSy... (key 1)
GEMINI_KEY_2=AIzaSy... (key 2)
GEMINI_KEY_3=AIzaSy... (key 3)
# Max: GEMINI_KEY_10
```

**How it works:**
```
Agent running...
  ├─ Use KEY_1 for Gemma 4-31B
  ├─ Hit rate limit? Rotate to KEY_2
  ├─ KEY_2 fails? Try KEY_3
  └─ All keys exhausted? Fallback to Gemini Flash-Lite
```

**Recommendation for i3 8GB:**
- Minimum: 2 keys
- Optimal: 3 keys
- Maximum: 5 keys (more than this = overhead)

---

## ⚡ Optimization for i3 8GB

### Memory-Conscious Setup

```python
# ✅ GOOD: Use Gemma 4-26B as DEFAULT (lighter than 31B)
DEFAULT_LLM_MODEL = "gemma-4-26b-a4b-it"  # MoE, only 3.8B active
CODEGEN_MODEL = "gemma-4-31b-it"           # Switch to 31B only when needed

# ❌ BAD: Always use Gemma 4-31B
DEFAULT_LLM_MODEL = "gemma-4-31b-it"  # Heavy, wastes RAM
```

### Browser Resource Management

```python
# .env
MAX_RAM_PERCENT=85       # Pause if RAM > 85%
MAX_CPU_PERCENT=90       # Pause if CPU > 90%

# Code (in main.py)
wait_for_resources()  # Check before each browser action
gc.collect()          # Force garbage collection after each task
```

### Proxy Configuration

```env
# ✅ GOOD: No proxy (faster, less RAM)
RESIDENTIAL_PROXIES=

# ❌ OK: 1-2 proxies max
RESIDENTIAL_PROXIES=http://user:pass@ip:port

# ❌ BAD: Too many proxies (eats RAM)
RESIDENTIAL_PROXIES=proxy1,proxy2,proxy3,proxy4,proxy5
```

---

## 🧪 Troubleshooting

### Issue: "API key not found" or "Invalid API key"

**Solution:**
```bash
# 1. Verify key format
echo $GEMINI_KEY_1  # Should show AIzaSy...

# 2. Test directly
python -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
model = genai.GenerativeModel('gemma-4-31b-it')
print('✅ Key valid')
"

# 3. Create new key at https://aistudio.google.com/apikey
```

### Issue: "Quota exceeded" or rate limit errors

**Solution:**
```bash
# Add more keys for rotation
# .env: Add GEMINI_KEY_2, GEMINI_KEY_3, etc
# Agent will automatically rotate keys

# Or check quota at: https://aistudio.google.com/

# Or wait 24 hours (daily quota resets)
```

### Issue: "Timeout" errors

**Solution:**
```bash
# 1. Check internet connection
ping 8.8.8.8

# 2. Try fallback model manually
python -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
response = model.generate_content('Test')
print(response.text)
"

# 3. Increase timeout in llm_config.py
LLM_MODELS['gemma-4-31b-it']['timeout'] = 300  # 5 minutes
```

### Issue: Browser not working (Playwright errors)

**Solution:**
```bash
# 1. Install/update Chromium
playwright install chromium

# 2. Test browser
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://google.com')
    print('✅ Browser working')
    browser.close()
"
```

---

## 📞 Support

**Resources:**
- Google AI Studio: https://aistudio.google.com/
- Gemma 4 Documentation: https://ai.google.dev/gemma
- API Reference: https://ai.google.dev/gemini-api/docs
- Community: https://discuss.ai.google.dev/

**Issues:**
- GitHub Issues: https://github.com/vraafi/Nexus-DualBrain-AI/issues
- Documentation: https://github.com/vraafi/Nexus-DualBrain-AI

---

## ✅ Verification Checklist

- [ ] Google AI Studio API key obtained
- [ ] .env configured with all GEMINI_KEY_* values
- [ ] Telegram bot created & IDs added to .env
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Tested Gemma 4-31B model
- [ ] Tested Gemma 4-26B model
- [ ] Tested web search functionality
- [ ] Browser testing passed (Playwright)
- [ ] Resource limits set appropriately for i3 8GB
- [ ] Multiple keys configured for rotation (optional but recommended)
- [ ] All tests passing

Once all ✅, ready to run: `python main.py`
