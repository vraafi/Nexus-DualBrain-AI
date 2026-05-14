# Setup Guide: Hermes Agent + Jules CLI + GitHub CLI
# Nexus DualBrain AI v2.0

## Arsitektur Yang Benar

```
Hermes Agent CLI (NousResearch)  ← Orchestrator utama
    ├── Baca SOUL.md, AGENTS.md, HEARTBEAT.md
    ├── Jalankan Skills dari .hermes/skills/
    ├── Telegram Gateway
    └── Skills memanggil:
        ├── Jules CLI  ← Autonomous coding (GitHub)
        └── GitHub CLI ← Repo management
```

---

## Step 1: Install Hermes Agent (NousResearch)

```bash
# Install Hermes Agent CLI
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Reload shell
source ~/.bashrc

# Verifikasi
hermes --version
hermes doctor
```

### Setup Hermes Agent
```bash
# Initialize dengan konfigurasi yang sudah ada
hermes setup

# Pilih model: gunakan Google/Gemini
hermes model

# Copy konfigurasi Nexus ke ~/.hermes/
cp -r ~/Nexus-DualBrain-AI/.hermes/skills/* ~/.hermes/skills/
cp ~/Nexus-DualBrain-AI/.hermes/hermes.json ~/.hermes/hermes.json
cp ~/Nexus-DualBrain-AI/SOUL.md ~/.hermes/SOUL.md
cp ~/Nexus-DualBrain-AI/AGENTS.md ~/.hermes/AGENTS.md
cp ~/Nexus-DualBrain-AI/HEARTBEAT.md ~/.hermes/HEARTBEAT.md

# Setup Telegram gateway
hermes gateway setup
```

### Environment Variables untuk Hermes
Edit `~/.hermes/.env`:
```bash
# Gemini API
GEMINI_KEY_1=your_gemini_key_here
GEMINI_KEY_2=your_gemini_key_2_here

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Target rate
TARGET_HOURLY_RATE=35
```

---

## Step 2: Install GitHub CLI

```bash
# Ubuntu/Debian (WSL)
sudo apt update
sudo apt install gh -y

# Atau via curl
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh -y
```

### Authenticate GitHub CLI
```bash
gh auth login

# Pilih:
# > GitHub.com
# > HTTPS
# > Yes (authenticate Git with GitHub credentials)
# > Login with a web browser
```

### Verifikasi
```bash
gh auth status
gh repo view vraafi/Nexus-DualBrain-AI
```

### Buat GitHub Labels untuk Jules
```bash
# Buat labels yang dibutuhkan di repo
gh label create "jules" --repo vraafi/Nexus-DualBrain-AI --color "0075ca" --description "Assigned to Jules AI"
gh label create "freelance-job" --repo vraafi/Nexus-DualBrain-AI --color "e4e669" --description "Active freelance job"
gh label create "sandbox-pass" --repo vraafi/Nexus-DualBrain-AI --color "0e8a16" --description "Passed sandbox test"
```

---

## Step 3: Install Jules CLI

```bash
# Install via npm
npm install -g @google/jules

# Verifikasi
jules --version
```

### Authenticate Jules
```bash
jules login
# Akan membuka browser untuk Google login
```

### Connect Jules ke GitHub Repo
1. Buka https://jules.google.com
2. Sign in dengan Google account
3. Klik **"Connect to GitHub Account"**
4. Authorize jules untuk akses repo `vraafi/Nexus-DualBrain-AI`

### Test Jules
```bash
# Test jules bisa akses repo
jules remote list --repo vraafi/Nexus-DualBrain-AI

# Test simple coding task
jules remote \
  --repo vraafi/Nexus-DualBrain-AI \
  --session "Create a simple hello_world.py script with a main() function and docstring. Save it to output/generated/test_hello.py"
```

---

## Step 4: Jalankan Nexus via Hermes Agent

### Mode 1: Hermes CLI (Rekomendasi)
```bash
# Set goal jangka panjang
hermes --goal "Cari job freelance Python di Upwork dan Fiverr. Ketika dapat job, gunakan Jules CLI untuk mengerjakan kode, test di sandbox, lalu deliver ke klien. Ulangi terus menerus. Target: $300/bulan."

# Atau TUI mode
hermes --tui
```

### Mode 2: Hermes dengan Python Backend (Fallback)
```bash
cd ~/Nexus-DualBrain-AI
source venv/bin/activate
python3 main.py
```

### Kontrol via Telegram
```
/status   - Lihat status agent
/pause    - Pause agent
/resume   - Lanjut
/earnings - Lihat pendapatan
/jobs     - Lihat jobs aktif
/think    - Trigger self-reflection
/skills   - Lihat skill templates
```

---

## Verifikasi Setup Lengkap

```bash
echo "=== Checking all tools ==="
hermes --version && echo "✅ Hermes OK" || echo "❌ Hermes NOT installed"
gh --version && echo "✅ GitHub CLI OK" || echo "❌ gh NOT installed"
jules --version && echo "✅ Jules CLI OK" || echo "❌ Jules NOT installed"
gh auth status && echo "✅ gh authenticated" || echo "❌ gh NOT authenticated"
jules remote list --repo vraafi/Nexus-DualBrain-AI 2>/dev/null && echo "✅ Jules connected to repo" || echo "❌ Jules NOT connected"
echo "=== Check complete ==="
```

---

## Workflow Lengkap AGI Loop

```
Hermes Agent (orchestrator)
    ↓
[Skill 01] Upwork Search → job ditemukan
    ↓
[Skill 04] Negotiate → contract accepted
    ↓
[Skill 09] GitHub CLI → gh issue create
    ↓
[Skill 05] Jules CLI → jules remote --session "implement issue #N"
    ↓ (Jules menulis kode, buat PR di GitHub)
[Skill 09] GitHub CLI → gh pr checkout
    ↓
[Skill 06] Sandbox Test → bwrap test
    ↓ (jika gagal: gh pr comment "please fix: ...")
[Skill 07] Deliver → kirim ke Upwork/Fiverr
    ↓
Hermes Memory → simpan ke ~/.hermes/memory/clients/
    ↓
Loop kembali ke Step 1
```
