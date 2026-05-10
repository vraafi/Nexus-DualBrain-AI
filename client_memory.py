"""
client_memory.py — Manajemen memori per-klien untuk Nexus DualBrain AI
Dipanggil oleh semua agent sebelum dan setelah interaksi dengan klien.
Terintegrasi dengan sistem memori OpenClaw (~/. openclaw/memory/clients/)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
MEMORY_BASE = os.path.expanduser("~/.openclaw/memory/clients")

CLIENT_TEMPLATE = """# Client: {username} ({platform})

## Info Dasar
- Platform: {platform}
- Username: {username}
- Nama: {name}
- Rating: {rating}
- Lokasi: {location}
- Bahasa: {language}

## Riwayat Job
| Tanggal | Job Title | Budget | Status | Revenue |
|---|---|---|---|---|

## Preferensi & Catatan
- (belum ada catatan)

## Riwayat Negosiasi
- (belum ada riwayat)

## Status Saat Ini
- Status: PROSPECT
- Job aktif: tidak ada
- Last contact: {last_contact}
"""


class ClientMemory:
    def __init__(self):
        os.makedirs(MEMORY_BASE, exist_ok=True)

    def _get_path(self, platform: str, username: str) -> str:
        dir_path = os.path.join(MEMORY_BASE, platform.lower())
        os.makedirs(dir_path, exist_ok=True)
        # Sanitize username untuk filename
        safe_username = "".join(c for c in username if c.isalnum() or c in "-_.")
        return os.path.join(dir_path, f"{safe_username}.md")

    def read(self, platform: str, username: str) -> str:
        """Baca memori klien. Jika tidak ada, kembalikan string kosong."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.error(f"[Memory] Gagal baca memori {platform}/{username}: {e}")
            return ""

    def create_if_not_exists(self, platform: str, username: str,
                              name: str = "", rating: str = "N/A",
                              location: str = "Unknown", language: str = "English") -> str:
        """Buat file memori baru jika belum ada."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
            content = CLIENT_TEMPLATE.format(
                username=username,
                platform=platform,
                name=name or username,
                rating=rating,
                location=location,
                language=language,
                last_contact=now
            )
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                logging.info(f"[Memory] File memori baru dibuat: {platform}/{username}")
            except Exception as e:
                logging.error(f"[Memory] Gagal buat file memori: {e}")
        return self.read(platform, username)

    def add_job(self, platform: str, username: str,
                job_title: str, budget: float, status: str, revenue: float = 0.0):
        """Tambah entri job ke riwayat klien."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            self.create_if_not_exists(platform, username)

        now = datetime.now(WIB).strftime("%Y-%m-%d")
        new_row = f"| {now} | {job_title} | ${budget:.0f} | {status} | ${revenue:.2f} |\n"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Sisipkan setelah header tabel
            insert_marker = "|---|---|---|---|---|\n"
            if insert_marker in content:
                content = content.replace(insert_marker, insert_marker + new_row)

            # Update Last contact
            content = self._update_field(content, "Last contact:", datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"))

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            logging.info(f"[Memory] Job ditambahkan ke memori {platform}/{username}: {job_title}")
        except Exception as e:
            logging.error(f"[Memory] Gagal update job: {e}")

    def add_negotiation_note(self, platform: str, username: str, note: str):
        """Tambah catatan negosiasi ke riwayat klien."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            self.create_if_not_exists(platform, username)

        now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M")
        new_note = f"- {now}: {note}\n"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Tambahkan setelah marker riwayat negosiasi
            marker = "## Riwayat Negosiasi\n"
            if marker in content:
                content = content.replace(marker, marker + new_note)
            else:
                content += f"\n{marker}{new_note}"

            content = self._update_field(content, "Last contact:", datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"))

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logging.error(f"[Memory] Gagal tambah catatan negosiasi: {e}")

    def update_status(self, platform: str, username: str, status: str, active_job: str = ""):
        """Update status klien saat ini."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            content = self._update_field(content, "- Status:", status)
            if active_job:
                content = self._update_field(content, "- Job aktif:", active_job)
            content = self._update_field(content, "- Last contact:", datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"))

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logging.error(f"[Memory] Gagal update status: {e}")

    def add_preference(self, platform: str, username: str, preference: str):
        """Tambah preferensi baru ke catatan klien."""
        path = self._get_path(platform, username)
        if not os.path.exists(path):
            self.create_if_not_exists(platform, username)

        marker = "## Preferensi & Catatan\n"
        new_pref = f"- {preference}\n"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Hapus placeholder jika masih ada
            content = content.replace("- (belum ada catatan)\n", "")

            if marker in content:
                content = content.replace(marker, marker + new_pref)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logging.error(f"[Memory] Gagal tambah preferensi: {e}")

    def get_context_for_llm(self, platform: str, username: str) -> str:
        """
        Ambil konteks klien yang ringkas untuk disertakan ke prompt LLM.
        Hanya ambil bagian penting: preferensi & status terkini.
        """
        content = self.read(platform, username)
        if not content:
            return f"Klien baru dari {platform}. Belum ada riwayat."

        # Ekstrak bagian penting saja (hemat token)
        sections = []
        for section in ["## Preferensi & Catatan", "## Status Saat Ini", "## Riwayat Negosiasi"]:
            if section in content:
                start = content.index(section)
                # Cari section berikutnya
                next_section = content.find("\n## ", start + len(section))
                if next_section > 0:
                    sections.append(content[start:next_section].strip())
                else:
                    sections.append(content[start:start+500].strip())  # max 500 char per section

        return "\n\n".join(sections) if sections else f"Klien dari {platform}, belum ada catatan detail."

    def _update_field(self, content: str, field_prefix: str, new_value: str) -> str:
        """Helper: update nilai field inline di markdown."""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith(field_prefix):
                lines[i] = f"{field_prefix} {new_value}"
                break
        return "\n".join(lines)

    def list_clients(self, platform: str = None) -> list:
        """List semua klien yang tersimpan di memori."""
        clients = []
        try:
            if platform:
                dirs = [os.path.join(MEMORY_BASE, platform.lower())]
            else:
                dirs = [os.path.join(MEMORY_BASE, d) for d in os.listdir(MEMORY_BASE)
                        if os.path.isdir(os.path.join(MEMORY_BASE, d))]

            for d in dirs:
                if not os.path.exists(d):
                    continue
                platform_name = os.path.basename(d)
                for f in os.listdir(d):
                    if f.endswith(".md"):
                        clients.append({
                            "platform": platform_name,
                            "username": f[:-3],
                            "path": os.path.join(d, f)
                        })
        except Exception as e:
            logging.error(f"[Memory] Gagal list clients: {e}")
        return clients
