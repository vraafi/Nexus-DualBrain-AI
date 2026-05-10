---
name: sandbox-test
description: "Test kode Python yang dihasilkan di bwrap sandbox yang aman: static analysis (flake8), eksekusi terisolasi, self-correction loop hingga 7 kali jika gagal, auto-fix via Gemini."
version: "1.0.0"
triggers:
  - "test kode"
  - "sandbox"
  - "jalankan sandbox"
  - "verifikasi kode"
tools:
  - exec
  - read
  - write
permissions:
  - file_write
  - shell_exec
---

# Skill: Sandbox Testing (bwrap isolation)

## Tujuan
Menguji kode yang digenerate di lingkungan sandbox bwrap yang aman dan terisolasi. Jika kode gagal, gunakan Gemini untuk auto-fix, ulangi hingga maksimal 7 kali.

## Prasyarat Sistem
- `bwrap` harus terinstall: `sudo apt-get install -y bubblewrap`
- Virtual environment sandbox sudah ada di `sandbox_env/`

## Langkah-Langkah

### 1. Baca metadata job dan path kode
```bash
read ~/Nexus-DualBrain-AI/output/job_queue.json
```
Ambil job dengan status `CODE_READY`.

### 2. Jalankan sandbox testing
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/sandbox_tool.py \
  --code-path "output/generated/<job_id>_code.py" \
  --job-id "<job_id>" \
  --max-attempts 7 \
  --timeout-minutes 15
```

Script akan:
1. Static analysis dengan flake8 (cegah syntax error)
2. Eksekusi di bwrap sandbox (isolated: no network, no host access)
3. Jika gagal: search DuckDuckGo untuk error solution
4. Auto-fix via Gemini 2.5 Flash
5. Ulangi hingga 7x atau sampai berhasil

### 3. Baca hasil testing
```bash
read ~/Nexus-DualBrain-AI/output/sandbox_results/<job_id>_result.json
```

### 4a. Jika testing BERHASIL (status: PASSED)
Update job_queue.json: status → `SANDBOX_PASSED`
Notifikasi: "Kode untuk '<job_title>' lulus sandbox testing. Siap untuk delivery."

### 4b. Jika testing GAGAL setelah 7 percobaan (status: FAILED)
Generate pesan permintaan maaf kepada klien:
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/codegen_tool.py \
  --action generate_apology \
  --job-id "<job_id>" \
  --platform "<platform>"
```
Update job_queue.json: status → `SANDBOX_FAILED`
Notifikasi Telegram: "PERLU INTERVENSI: Sandbox gagal untuk '<job_title>' setelah 7 percobaan."

### 5. Cleanup file sementara
```bash
cd ~/Nexus-DualBrain-AI && python3 tools/sandbox_tool.py --action cleanup --job-id "<job_id>"
```

## Keamanan Sandbox (bwrap)
- No network access saat testing (kode tidak bisa call internet)
- No read access ke host filesystem
- No write access ke luar direktori sandbox
- Environment variables tidak bocor ke kode yang ditest
- Timeout maksimal 15 menit per percobaan

## Output
- File hasil: `output/sandbox_results/<job_id>_result.json`
- File kode final (jika berhasil): `output/generated/<job_id>_final.py`
- job_queue.json diupdate: status SANDBOX_PASSED atau SANDBOX_FAILED
