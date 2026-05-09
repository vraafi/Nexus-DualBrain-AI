# Nexus DualBrain AI + OpenClaw

**Autonomous freelance AI agent** untuk Upwork, Fiverr, dan Freelancer —  
dioptimalkan untuk hardware terbatas: **Intel i3 Gen 8 · 8GB RAM · 256GB SSD**.

---

## Arsitektur DualBrain

```
┌─────────────────────────────────────────────────────────┐
│                    NEXUS DUALBRAIN AI                   │
├──────────────────────┬──────────────────────────────────┤
│   Brain #1           │   Brain #2                       │
│   REASONING          │   EXECUTION                      │
│   Gemini 2.5 Pro     │   Local Python + bwrap sandbox   │
│   (via REST API)     │   (ringan, aman, tanpa Docker)   │
│   • Job screening    │   • Code testing                 │
│   • Negosiasi        │   • Self-correction loop         │
│   • Code generation  │   • Static analysis (flake8)     │
└──────────────────────┴──────────────────────────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                  OPENCLAW GATEWAY                       │
│   Telegram ←→ OpenClaw ←→ Agent Controller             │
│   /status  /pause  /resume  /earnings  /help           │
└─────────────────────────────────────────────────────────┘
```

## Model LLM yang Digunakan

| Model | Kegunaan | Endpoint |
|---|---|---|
| `gemini-2.5-pro` | Code generation, analisis mendalam | Recommended |
| `gemini-2.5-flash` | Screening job, negosiasi (default) | Fast & hemat |
| `gemini-2.0-flash` | Fallback jika quota habis | Tercepat |

## Cara Install & Jalankan

### 1. Persiapan sistem

```bash
sudo apt-get update && sudo apt-get install -y bubblewrap python3-pip
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Konfigurasi .env

```bash
cp .env.example .env
# Edit .env dan isi semua API key
nano .env
```

Nilai wajib di `.env`:
```env
GEMINI_KEY_1=your_gemini_api_key        # dari aistudio.google.com/apikey
TELEGRAM_BOT_TOKEN=your_bot_token       # dari @BotFather di Telegram
TELEGRAM_CHAT_ID=your_chat_id           # ID Telegram kamu
VAULT_PASSWORD=password_kuat_16_char    # untuk enkripsi vault kredensial

# OpenClaw (opsional tapi disarankan)
OPENCLAW_API_KEY=your_openclaw_key      # dari app.getopenclaw.ai
```

### 4. Simpan kredensial platform ke vault

```python
python3 -c "
from identity_manager import IdentityManager
m = IdentityManager()
m.save_credential('upwork', 'email@kamu.com', 'password_upwork')
m.save_credential('fiverr', 'email@kamu.com', 'password_fiverr')
m.save_credential('freelancer', 'email@kamu.com', 'password_freelancer')
print('Vault berhasil diisi!')
"
```

### 5. Jalankan agent

```bash
python main.py
```

### 6. Kontrol agent via Telegram

Setelah agent jalan, kirim perintah ke Telegram bot kamu:

| Perintah | Fungsi |
|---|---|
| `/status` | Status agent & uptime |
| `/pause` | Jeda agent sementara |
| `/resume` | Lanjutkan agent |
| `/earnings` | Ringkasan pendapatan |
| `/help` | Daftar semua perintah |

### 7. Lihat dashboard (opsional)

```bash
python dashboard.py
```

---

## Alur Kerja Agent

```
Start
  │
  ├─► Crash Recovery (lanjut dari langkah terakhir jika ada crash)
  │
  ├─► Inbox Check (cek negosiasi Upwork yang aktif)
  │
  ├─► Freelance Orchestrator
  │     Upwork (7 jam) → Fiverr (6 jam) → Freelancer (5 jam)
  │     + EmailMonitor background thread (interupsi jika ada order masuk)
  │     + Jadwal istirahat: 11:00–17:00 WIB (saat klien Amerika tidur)
  │
  ├─► Code Generation (Gemini 2.5 Pro + web search otomatis)
  │
  ├─► Sandbox Testing (bwrap isolation + self-correction loop)
  │
  └─► Delivery ke platform
```

## Hardware & Resource Management

Agent dirancang khusus untuk **i3 Gen 8, 8GB RAM**:

- `wait_for_resources()` → pause jika RAM >85% atau CPU >90%
- `gc.collect()` → paksa garbage collection setelah setiap fase browser
- Single Chromium process (`--single-process` flag)
- Model default `gemini-2.5-flash` (hemat memory, tetap capable)
- Model codegen `gemini-2.5-pro` hanya dipanggil saat generate kode

## Catatan Penting (Baca Sebelum Pakai)

> ⚠️ **Upwork, Fiverr, dan Freelancer melarang otomasi di ToS mereka.**  
> Penggunaan agent ini berisiko penangguhan akun jika terdeteksi.  
> Agent dilengkapi `playwright-stealth` dan `ghost-cursor` untuk meminimalisir deteksi,  
> namun tidak ada jaminan 100% tidak terdeteksi.  
>
> **Gunakan dengan risiko sendiri. Pantau selalu via Telegram.**

---

## File Utama

| File | Fungsi |
|---|---|
| `main.py` | Entry point & workflow engine |
| `openclaw_agent.py` | OpenClaw + Telegram command handler |
| `api_client.py` | Gemini API client + multi-key rotation |
| `llm_config.py` | Konfigurasi model Gemini |
| `freelance_orchestrator.py` | Rotasi platform & email monitor |
| `browser_agent.py` | Playwright stealth browser |
| `sandbox_tester.py` | bwrap sandbox + self-correction |
| `identity_manager.py` | Vault kredensial terenkripsi |
| `financial_tracker.py` | Pelacak pendapatan |
| `database.py` | SQLite state persistence + crash recovery |
