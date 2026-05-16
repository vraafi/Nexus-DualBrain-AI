"""
patch_browser_use.py — Nexus DualBrain AI
==========================================
Patch permanen browser-use v0.12.x agar Gemma IT models bisa dipakai.

Cara pakai:
    python3 patch_browser_use.py

Script ini akan:
  1. Menemukan instalasi browser-use di venv/site-packages secara otomatis
  2. Membaca file asli dan mengecek apakah patch sudah ada
  3. Menerapkan patch jika belum ada (tidak menimpa ulang jika sudah)
  4. Memverifikasi hasilnya

Root cause "Result failed X/6 times: items":
  Gemma IT models tidak didaftarkan sebagai non-function-calling model di
  browser-use. Akibatnya browser-use mengirim tool schema ke API Gemma,
  Gemma merespons dengan raw JSON string, dan AgentOutput parser gagal.

Fix yang diterapkan:
  - agent.py       : tambah 'gemma' ke daftar non-function-calling check
  - utils.py       : tambah kondisi Gemma ke convert_input_messages()

Referensi:
  https://github.com/browser-use/browser-use/issues/1237
  https://github.com/browser-use/browser-use/issues/1458
"""

import sys
import os
import re
import shutil
import importlib.util
from pathlib import Path


PATCH_MARKER = "# [NEXUS-GEMMA-PATCH-APPLIED]"

COLORS = {
    "ok":   "\033[92m",
    "warn": "\033[93m",
    "err":  "\033[91m",
    "info": "\033[94m",
    "bold": "\033[1m",
    "reset":"\033[0m",
}

def c(color, text):
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"


def find_browser_use_root() -> Path:
    """Cari direktori instalasi browser-use secara otomatis."""
    spec = importlib.util.find_spec("browser_use")
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])
    raise FileNotFoundError(
        "browser-use tidak ditemukan. Pastikan virtual environment aktif "
        "dan browser-use sudah terinstall: pip install browser-use"
    )


def backup_file(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".nexus_backup")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(c("info", f"  Backup dibuat: {backup.name}"))
    return backup


def already_patched(content: str) -> bool:
    return PATCH_MARKER in content


def patch_agent_py(bu_root: Path) -> bool:
    """
    Patch browser_use/agent/agent.py:
    Tambah 'gemma' ke logika non-function-calling model detection.
    """
    candidates = [
        bu_root / "agent" / "agent.py",
        bu_root / "agent.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        print(c("warn", "  agent.py tidak ditemukan — skip patch ini."))
        return False

    content = target.read_text(encoding="utf-8")

    if already_patched(content):
        print(c("ok", f"  agent.py: patch sudah diterapkan sebelumnya."))
        return True

    backup_file(target)

    # Cari pola yang mendeteksi non-function-calling model (deepseek, qwen, dll)
    # dan tambahkan 'gemma' ke dalamnya.
    patterns = [
        # Pola: list/tuple dengan deepseek dan/atau qwen
        (
            r"(non_fc_models\s*=\s*\[)(.*?)(deepseek.*?)(])",
            lambda m: m.group(1) + m.group(2) + m.group(3) + ", 'gemma'" + m.group(4),
        ),
        # Pola: kondisi if dengan deepseek-r1
        (
            r"('deepseek-r1'\s+in\s+model_name)",
            lambda m: m.group(1) + " or 'gemma' in model_name",
        ),
        (
            r'("deepseek-r1"\s+in\s+model_name)',
            lambda m: m.group(1) + ' or "gemma" in model_name',
        ),
        # Pola: any(m in model_name for m in [...])
        (
            r"(any\([^)]*\[)([^\]]*deepseek[^\]]*?)(\])",
            lambda m: m.group(1) + m.group(2) + ', "gemma"' + m.group(3),
        ),
    ]

    patched = False
    for pattern, replacer in patterns:
        new_content, count = re.subn(pattern, replacer, content, flags=re.DOTALL)
        if count > 0:
            content = new_content
            patched = True
            break

    if not patched:
        # Fallback: cari method _is_non_function_calling_model dan timpa isinya
        fc_method_pattern = r"(def _is_non_function_calling_model\(self\)[^:]*:)(.*?)(return (?:True|False|any|model_name|self))"
        match = re.search(fc_method_pattern, content, re.DOTALL)
        if match:
            replacement = (
                match.group(1)
                + "\n        model_obj = getattr(self, 'llm', None) or getattr(self, 'model', None)\n"
                + "        if not model_obj:\n            return False\n"
                + "        name = (getattr(model_obj, 'model_name', None) or getattr(model_obj, 'model', '')).lower()\n"
                + "        return any(kw in name for kw in ('deepseek-r1', 'qwen', 'gemma'))\n"
                + "        # (original below, overridden by Nexus patch)\n"
            )
            content = content[:match.start()] + replacement + content[match.end():]
            patched = True

    if not patched:
        print(c("warn", "  agent.py: pola target tidak ditemukan. Versi browser-use mungkin berbeda."))
        print(c("warn", "  Lapis 2 (utils.py) tetap akan diterapkan."))
        return False

    content = content + f"\n{PATCH_MARKER}\n"
    target.write_text(content, encoding="utf-8")
    print(c("ok", f"  agent.py: ✅ patch berhasil diterapkan."))
    return True


def patch_utils_py(bu_root: Path) -> bool:
    """
    Patch browser_use/agent/message_manager/utils.py:
    Tambah kondisi Gemma ke convert_input_messages().
    """
    candidates = [
        bu_root / "agent" / "message_manager" / "utils.py",
        bu_root / "agent" / "utils.py",
        bu_root / "utils.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        print(c("warn", "  utils.py tidak ditemukan — skip patch ini."))
        return False

    content = target.read_text(encoding="utf-8")

    if already_patched(content):
        print(c("ok", f"  utils.py: patch sudah diterapkan sebelumnya."))
        return True

    backup_file(target)

    # Cari fungsi convert_input_messages dan tambahkan kondisi Gemma
    # sebelum kondisi deepseek yang ada.
    pattern = r"(def convert_input_messages\([^)]*\)[^:]*:.*?)(if\s+model_name\s*==\s*[\"']deepseek-reasoner[\"']|if\s+[\"']deepseek-r1[\"']\s+in\s+model_name)"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        # Sisipkan kondisi Gemma tepat sebelum blok deepseek
        insert_pos = match.start(2)
        gemma_block = (
            "# [Nexus Gemma Patch] Gemma IT memakai non-function-calling path\n"
            "    if model_name and 'gemma' in model_name.lower() and '-it' in model_name.lower():\n"
            "        converted = _convert_messages_for_non_function_calling_models(input_messages)\n"
            "        merged = _merge_successive_messages(converted, HumanMessage)\n"
            "        merged = _merge_successive_messages(merged, AIMessage)\n"
            "        return merged\n"
            "    "
        )
        content = content[:insert_pos] + gemma_block + content[insert_pos:]
        content = content + f"\n{PATCH_MARKER}\n"
        target.write_text(content, encoding="utf-8")
        print(c("ok", f"  utils.py: ✅ patch berhasil diterapkan."))
        return True

    # Fallback: cari kondisi dengan deepseek-r1 saja
    pattern2 = r"('deepseek-r1'\s+in\s+model_name|\"deepseek-r1\"\s+in\s+model_name)"
    match2 = re.search(pattern2, content)
    if match2:
        old = match2.group(0)
        new = old + "\n        or ('gemma' in model_name.lower() and '-it' in model_name.lower())"
        content = content.replace(old, new, 1)
        content = content + f"\n{PATCH_MARKER}\n"
        target.write_text(content, encoding="utf-8")
        print(c("ok", f"  utils.py: ✅ patch (fallback) berhasil diterapkan."))
        return True

    print(c("warn", "  utils.py: fungsi convert_input_messages tidak ditemukan dengan pola yang dikenal."))
    print(c("warn", "  Coba jalankan ulang setelah update: pip install --upgrade browser-use"))
    return False


def verify_patches(bu_root: Path):
    """Verifikasi patch sudah ada di file."""
    print(f"\n{c('bold', 'Verifikasi:')}")
    for rel in ["agent/agent.py", "agent.py", "agent/message_manager/utils.py", "agent/utils.py"]:
        path = bu_root / rel
        if path.exists():
            content = path.read_text(encoding="utf-8")
            status = c("ok", "✅ patched") if already_patched(content) else c("warn", "⚠ belum di-patch")
            print(f"  {path.name}: {status}")


def main():
    print(c("bold", "\n" + "=" * 60))
    print(c("bold", " Nexus DualBrain AI — browser-use Gemma IT Patcher"))
    print(c("bold", "=" * 60))

    try:
        bu_root = find_browser_use_root()
        print(c("info", f"\nbrowser-use ditemukan di:"))
        print(f"  {bu_root}\n")
    except FileNotFoundError as e:
        print(c("err", f"\n❌ {e}"))
        sys.exit(1)

    print(c("bold", "Menerapkan patch...\n"))

    r1 = patch_agent_py(bu_root)
    r2 = patch_utils_py(bu_root)

    verify_patches(bu_root)

    print()
    if r1 or r2:
        print(c("ok", "✅ Patch selesai! Jalankan ulang: python3 main.py"))
        print(c("info", "\nLog yang menandakan berhasil saat main.py dijalankan:"))
        print('  INFO [browser_agent] ✅ Lapis 1 patch: Agent._is_non_function_calling_model ...')
        print('  INFO [browser_agent] ✅ Lapis 2 patch: convert_input_messages diperbarui ...')
        print(c("info", "\nJika patch tidak menyelesaikan masalah, jalankan:"))
        print("  pip install --upgrade browser-use")
        print("  python3 patch_browser_use.py")
    else:
        print(c("warn", "⚠ Tidak ada patch yang berhasil diterapkan."))
        print(c("info", "Coba langkah manual:"))
        print("  1. pip install --upgrade browser-use")
        print("  2. python3 patch_browser_use.py")

    print(c("bold", "\n" + "=" * 60 + "\n"))


if __name__ == "__main__":
    main()
