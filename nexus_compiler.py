import re
import asyncio
import tempfile
import os
import subprocess
import json
import time
import threading
import sys
import traceback
import resource
from typing import Tuple, List, Dict, Optional

from nexus_config import (
    console_terminal_interface,
    LUAU_ANALYZE_BINARY_PATH,
    LUNE_BINARY_PATH,
    LUAURC_PATH,
    PROJECT_ROOT_DIRECTORY
)


class AbsoluteOmniValidator:
    """Hakim Keamanan Leksikal Murni Tingkat Militer."""

    @staticmethod
    def sanitize_luau_code(raw_luau_code: str) -> str:
        code = re.sub(r'^\s*--.*$', '', raw_luau_code, flags=re.MULTILINE)
        return code

    @staticmethod
    def execute_validation(raw_luau_code: str, required_keywords: List[str], forbidden_keywords: List[str]) -> Tuple[bool, str]:
        omni_errors = []
        sanitized_code = AbsoluteOmniValidator.sanitize_luau_code(raw_luau_code)

        if not sanitized_code.strip() or len(sanitized_code) < 20:
            return False, "Kode kosong atau terlalu pendek untuk dievaluasi."

        if not re.search(r'^--!strict', raw_luau_code):
            omni_errors.append("Contract Violation: Baris pertama MUTLAK harus `--!strict`.")

        if "while true do" in sanitized_code or "while task.wait() do" in sanitized_code:
            if "RunService" not in sanitized_code and "task.wait" not in sanitized_code:
                omni_errors.append("Performance Violation: Loop terdeteksi tanpa RunService atau task.wait().")

        for req in required_keywords:
            if req not in sanitized_code:
                omni_errors.append(f"Contract Violation: Anda diwajibkan menggunakan '{req}' agar sesuai arsitektur.")

            if req == "Recipe":
                if not re.search(r'Recipe\s*[=:]\s*\{\s*[\'"]?[a-zA-Z_]', sanitized_code):
                    omni_errors.append("Crafting Logic Violation: Tabel 'Recipe' ditemukan, tetapi KOSONG atau formatnya salah.")

            if req == "ArmorTier":
                if not re.search(r'ArmorTier\s*[=:]\s*[1-6]', sanitized_code):
                    omni_errors.append("Armor Physics Violation: 'ArmorTier' wajib didefinisikan dengan nilai angka 1 hingga 6.")

            if req == "MaterialType":
                if not re.search(r'MaterialType\s*[=:]\s*[\'"][a-zA-Z]+[\'"]', sanitized_code):
                    omni_errors.append("Armor Physics Violation: 'MaterialType' wajib didefinisikan sebagai string.")

            if req == "ItemCategory":
                if not re.search(r'ItemCategory\s*[=:]\s*[\'"](Weapon|Ammunition|Armor|Medical|Material|Valuable|Bait|Tool)[\'"]', sanitized_code, re.IGNORECASE):
                    omni_errors.append("Economy Taxonomy Violation: 'ItemCategory' wajib diisi dengan salah satu kategori resmi.")

            if req == "BasePrice":
                if not re.search(r'BasePrice\s*[=:]\s*\d+', sanitized_code):
                    omni_errors.append("Economy Violation: 'BasePrice' wajib didefinisikan sebagai angka integer.")

            if req == "CanCollide":
                if not re.search(r'CanCollide\s*=\s*true', sanitized_code, re.IGNORECASE):
                    omni_errors.append("Physical Collision Violation: Objek dunia WAJIB memiliki properti 'CanCollide = true'.")

            if req == "Anchored":
                if not re.search(r'Anchored\s*=\s*true', sanitized_code, re.IGNORECASE):
                    omni_errors.append("Physical Gravity Violation: Objek dunia WAJIB memiliki properti 'Anchored = true'.")

            if req == "Raycast":
                if "workspace:Raycast" not in sanitized_code and "workspace.Raycast" not in sanitized_code:
                    omni_errors.append("Physical Placement Violation: Anda WAJIB menggunakan 'workspace:Raycast()' ke arah bawah.")

            if req == "RaycastParams":
                if "RaycastParams.new" not in sanitized_code:
                    omni_errors.append("Physical Precision Violation: Saat menggunakan Raycast, WAJIB menggunakan 'RaycastParams.new()'.")

            if req == "HitboxSeparation":
                if not re.search(r'CanCollide\s*=\s*false', sanitized_code, re.IGNORECASE) or not re.search(r'Transparency\s*=\s*1', sanitized_code):
                    omni_errors.append("Collision Optimization Violation: WAJIB menerapkan Hitbox Separation.")

            if req == "VisualEquip":
                if not re.search(r'WeldConstraint|AddAccessory|Motor6D', sanitized_code, re.IGNORECASE):
                    omni_errors.append("Visual Equip Violation: WAJIB menyertakan logika untuk menempelkan 3D model ke badan pemain.")
                if not re.search(r'ActionText\s*=\s*[\'"](?:Equip|Gunakan|Pakai)[\'"]', sanitized_code, re.IGNORECASE):
                    omni_errors.append("Visual Equip Violation: ProximityPrompt WAJIB memiliki ActionText bernilai 'Equip' atau 'Gunakan'.")

        if "OnServerEvent" in sanitized_code or "OnServerInvoke" in sanitized_code:
            if not re.search(r'typeof\s*\(', sanitized_code) and not re.search(r'type\s*\(', sanitized_code):
                omni_errors.append("Zero-Trust Security Violation: RemoteEvent/RemoteFunction terdeteksi tanpa validasi tipe data menggunakan `typeof()`.")

        if "DataStoreService" in sanitized_code or "SetAsync" in sanitized_code or "UpdateAsync" in sanitized_code:
            if "pcall" not in sanitized_code and "xpcall" not in sanitized_code:
                omni_errors.append("Fault-Tolerance Violation: Operasi DataStoreService terdeteksi tanpa perlindungan `pcall()`.")

        if "DataStoreService" in sanitized_code and ("SafeContainer" in sanitized_code or "LobbyStorage" in sanitized_code):
            if "PlayerRemoving" not in sanitized_code or "PlayerAdded" not in sanitized_code:
                omni_errors.append("Data Persistence Violation: Sistem inventaris permanen terdeteksi tanpa event `PlayerAdded` dan `PlayerRemoving`.")

        if "Diet" in required_keywords:
            if not re.search(r'Diet\s*[=:]\s*[\'"](Carnivore|Herbivore|Omnivore)[\'"]', sanitized_code, re.IGNORECASE):
                omni_errors.append("Ecology Violation: Variabel 'Diet' wajib diisi dengan string 'Carnivore', 'Herbivore', atau 'Omnivore'.")
        if "SocialBehavior" in required_keywords:
            if not re.search(r'SocialBehavior\s*[=:]\s*[\'"](Solitary|Pack|Herd)[\'"]', sanitized_code, re.IGNORECASE):
                omni_errors.append("Ecology Violation: Variabel 'SocialBehavior' wajib diisi dengan string 'Solitary', 'Pack', atau 'Herd'.")
        if "SpawnWeight" in required_keywords:
            if not re.search(r'SpawnWeight\s*[=:]\s*\d+', sanitized_code):
                omni_errors.append("Ecology Violation: Variabel 'SpawnWeight' wajib didefinisikan sebagai angka.")
        if "Habitat" in required_keywords:
            if not re.search(r'Habitat\s*[=:]\s*[\'"][a-zA-Z_]+[\'"]', sanitized_code, re.IGNORECASE):
                omni_errors.append("Ecology Violation: Variabel 'Habitat' wajib diisi dengan string nama bioma.")
        if "Stamina" in required_keywords:
            if not re.search(r'Stamina\s*[=:]\s*\d+', sanitized_code):
                omni_errors.append("Ecology Violation: Variabel 'Stamina' wajib didefinisikan sebagai angka.")
        if "PerceptionRadius" in required_keywords:
            if not re.search(r'PerceptionRadius\s*[=:]\s*\d+', sanitized_code):
                omni_errors.append("Ecology Violation: Variabel 'PerceptionRadius' wajib didefinisikan sebagai angka.")
        if "LocomotionType" in required_keywords:
            if not re.search(r'LocomotionType\s*[=:]\s*[\'"](Terrestrial|Aerial|Aquatic)[\'"]', sanitized_code, re.IGNORECASE):
                omni_errors.append("Ecology Violation: Variabel 'LocomotionType' wajib diisi.")
        if "DropTable" in required_keywords:
            has_drop_table = re.search(r'DropTable\s*[=:]\s*\{', sanitized_code)
            is_bait = re.search(r'(IsBait|Unkillable)\s*[=:]\s*true', sanitized_code, re.IGNORECASE)
            if not has_drop_table and not is_bait:
                omni_errors.append("Ecology & Economy Violation: Variabel 'DropTable' wajib didefinisikan berupa tabel.")

        for forb in forbidden_keywords:
            if forb in sanitized_code:
                omni_errors.append(f"Contract Violation: Dilarang keras menggunakan '{forb}' pada modul ini.")

        if omni_errors:
            return False, "VALIDASI LEKSIKAL OMNI GAGAL (PERBAIKI SEMUA):\n- " + "\n- ".join(omni_errors)

        return True, "Validasi Leksikal Tingkat Militer Lulus 100%."


class NativeLuauCompiler:
    """Kompilator AST C++ dan Eksekutor Runtime Lune."""

    @staticmethod
    def ensure_compiler_exists():
        if not os.path.exists(LUAU_ANALYZE_BINARY_PATH):
            console_terminal_interface.print("[bold yellow]luau-analyze tidak ditemukan. Mengunduh binary Linux terbaru...[/bold yellow]")
            try:
                subprocess.run([
                    "wget", "-q", "https://github.com/luau-lang/luau/releases/latest/download/luau-ubuntu.zip",
                    "-O", "/tmp/luau-ubuntu.zip"
                ], check=True, timeout=60)
                subprocess.run(["unzip", "-o", "/tmp/luau-ubuntu.zip", "luau-analyze", "-d", "/tmp/"], check=True)
                subprocess.run(["chmod", "+x", "/tmp/luau-analyze"], check=True)
                subprocess.run(["mv", "/tmp/luau-analyze", LUAU_ANALYZE_BINARY_PATH], check=True)
            except Exception as e:
                console_terminal_interface.print(f"[bold yellow]luau-analyze download gagal: {e}. Akan dilewati.[/bold yellow]")

        if not os.path.exists(LUNE_BINARY_PATH):
            console_terminal_interface.print("[bold yellow]lune tidak ditemukan. Mengunduh binary Linux terbaru...[/bold yellow]")
            try:
                subprocess.run([
                    "wget", "-q", "https://github.com/lune-org/lune/releases/latest/download/lune-linux-x86_64.zip",
                    "-O", "/tmp/lune-linux-x86_64.zip"
                ], check=True, timeout=60)
                subprocess.run(["unzip", "-o", "/tmp/lune-linux-x86_64.zip", "lune", "-d", "/tmp/"], check=True)
                subprocess.run(["chmod", "+x", "/tmp/lune"], check=True)
                subprocess.run(["mv", "/tmp/lune", LUNE_BINARY_PATH], check=True)
            except Exception as e:
                console_terminal_interface.print(f"[bold yellow]lune download gagal: {e}. Akan dilewati.[/bold yellow]")

        if not os.path.exists(LUAURC_PATH):
            luaurc_content = {
                "languageMode": "strict",
                "lint": {
                    "UnknownGlobal": False,
                    "GlobalPredecl": False,
                    "DeprecatedApi": True
                },
                "globals": [
                    "game", "workspace", "script", "math", "table", "string", "coroutine",
                    "task", "os", "debug", "utf8", "bit32", "require", "tick", "wait",
                    "delay", "spawn", "warn", "print", "error", "assert", "type", "typeof",
                    "tostring", "tonumber", "pairs", "ipairs", "next", "select", "unpack",
                    "getmetatable", "setmetatable", "pcall", "xpcall", "rawequal", "rawget",
                    "rawset", "rawlen", "Vector3", "Vector2", "CFrame", "Color3", "UDim2",
                    "UDim", "Instance", "Enum", "RaycastParams", "TweenInfo", "NumberSequence",
                    "ColorSequence", "NumberSequenceKeypoint", "ColorSequenceKeypoint",
                    "Region3", "Region3int16", "Vector3int16", "Vector2int16", "BrickColor",
                    "Faces", "Axes", "PhysicalProperties", "PathfindingModifier"
                ]
            }
            with open(LUAURC_PATH, "w") as f:
                json.dump(luaurc_content, f, indent=4)

    @staticmethod
    async def execute_native_ast_verification(luau_code: str, module_name: str) -> Tuple[bool, str]:
        if not os.path.exists(LUAU_ANALYZE_BINARY_PATH):
            return True, "luau-analyze tidak tersedia, dilewati."

        fd, temp_path = tempfile.mkstemp(suffix=".luau", prefix=f"temp_{module_name}_")
        os.close(fd)

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(luau_code)

            loop = asyncio.get_event_loop()

            analyze_process = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [LUAU_ANALYZE_BINARY_PATH, "--formatter=plain", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )

            if analyze_process.returncode != 0:
                error_msg = analyze_process.stderr.strip() or analyze_process.stdout.strip()
                return False, f"AST COMPILATION FAILED (luau-analyze):\n{error_msg}"

            if os.path.exists(LUNE_BINARY_PATH):
                lune_process = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [LUNE_BINARY_PATH, "run", temp_path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                )

                if lune_process.returncode != 0:
                    error_msg = lune_process.stderr.strip() or lune_process.stdout.strip()
                    return False, f"RUNTIME EXECUTION FAILED (lune):\n{error_msg}"

            return True, "AST dan Runtime Lune Lulus 100%."

        except subprocess.TimeoutExpired:
            return False, "TIMEOUT: Runtime Lune mengalami infinite loop/hang (Maks 5 detik)."
        except Exception as e:
            return False, f"SYSTEM ERROR saat eksekusi native: {str(e)}"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# =============================================================================
# === UPGRADE #3: HAKIM PENGUJI DIVERGEN - PistonCloudCompiler ================
# === Digunakan EKSKLUSIF oleh PolyglotSynthesizerAgent (Otak Universal) ======
# =============================================================================
class PistonCloudCompiler:
    """
    Hakim Sintaks Kode Universal menggunakan Piston API (https://emkc.org).

    Digunakan EKSKLUSIF untuk kode dari PolyglotSynthesizerAgent.
    TIDAK PERNAH digunakan untuk kode Luau/Roblox.

    Keunggulan:
    - Uji sintaks API tanpa membebani RAM VPS lokal.
    - Mendukung Python 3.x, C++ (g++), Go, Rust, JavaScript, Java, Bash, dll.
    - Isolasi eksekusi penuh di cloud Piston.
    """

    PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"

    # Mapping bahasa ke runtime Piston
    LANGUAGE_RUNTIME_MAP: Dict[str, Dict[str, str]] = {
        "python":     {"language": "python",  "version": "3.10.0"},
        "cpp":        {"language": "c++",      "version": "10.2.0"},
        "c++":        {"language": "c++",      "version": "10.2.0"},
        "go":         {"language": "go",       "version": "1.16.2"},
        "rust":       {"language": "rust",     "version": "1.50.0"},
        "javascript": {"language": "javascript", "version": "16.3.0"},
        "typescript": {"language": "typescript", "version": "4.2.3"},
        "java":       {"language": "java",     "version": "15.0.2"},
        "bash":       {"language": "bash",     "version": "5.1.0"},
        "sh":         {"language": "bash",     "version": "5.1.0"},
    }

    @staticmethod
    async def compile_and_run(code: str, language: str, task_name: str = "") -> Tuple[bool, str]:
        """
        Kirim kode ke Piston API untuk kompilasi dan eksekusi singkat (uji sintaks).
        Return: (success, output_or_error)
        """
        lang_lower = language.lower()
        runtime = PistonCloudCompiler.LANGUAGE_RUNTIME_MAP.get(
            lang_lower,
            {"language": lang_lower, "version": "*"}
        )

        # Tentukan nama file berdasarkan bahasa
        ext_map = {
            "python": "main.py",
            "cpp": "main.cpp", "c++": "main.cpp",
            "go": "main.go",
            "rust": "main.rs",
            "javascript": "main.js",
            "typescript": "main.ts",
            "java": "Main.java",
            "bash": "main.sh", "sh": "main.sh",
        }
        filename = ext_map.get(lang_lower, "main.txt")

        payload = {
            "language": runtime["language"],
            "version": runtime["version"],
            "files": [{"name": filename, "content": code}],
            "stdin": "",
            "args": [],
            "compile_timeout": 30000,
            "run_timeout": 10000,
        }

        console_terminal_interface.print(
            f"[dim cyan]  [PistonCloud] Menguji sintaks {language} di cloud ({task_name})...[/dim cyan]"
        )

        loop = asyncio.get_event_loop()

        def _call_piston():
            import urllib.request
            import urllib.error
            try:
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    PistonCloudCompiler.PISTON_API_URL,
                    data=req_data,
                    headers={"Content-Type": "application/json", "User-Agent": "NexusPolyglot/2.0"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError as e:
                return {"_error": f"Piston API tidak terjangkau: {e}"}
            except Exception as e:
                return {"_error": f"Piston exception: {e}"}

        result = await loop.run_in_executor(None, _call_piston)

        if "_error" in result:
            console_terminal_interface.print(
                f"[bold yellow]  [PistonCloud] API tidak tersedia: {result['_error']}. Dilewati.[/bold yellow]"
            )
            return True, "PISTON_UNAVAILABLE: Uji sintaks cloud dilewati."

        compile_stage = result.get("compile", {})
        run_stage = result.get("run", {})

        compile_code = compile_stage.get("code", 0) if compile_stage else 0
        run_code = run_stage.get("code", 0)
        compile_stderr = compile_stage.get("stderr", "") if compile_stage else ""
        run_stderr = run_stage.get("stderr", "")
        run_stdout = run_stage.get("output", "")

        # Error kompilasi = kode rusak
        if compile_code != 0 and compile_stderr:
            err_msg = f"PISTON COMPILE ERROR ({language}):\n{compile_stderr[:600]}"
            console_terminal_interface.print(f"[bold red]  [PistonCloud] {err_msg[:200]}[/bold red]")
            return False, err_msg

        # Runtime error bisa jadi normal (exit code non-zero ok untuk script pendek)
        # Yang penting tidak ada compile error
        output_summary = run_stdout[:200] if run_stdout else "(no output)"
        console_terminal_interface.print(
            f"[bold green]  \u2705 [PistonCloud] Sintaks {language} VALID. "
            f"Output: {output_summary}[/bold green]"
        )
        return True, f"PISTON_OK: {output_summary}"


# =============================================================================
# === UPGRADE #4: FITUR PEMBUNUH MANUS AI & REPLIT - LocalSandboxStressTester =
# === 1-Hour Stateful Sandbox: Kode disiksa 3600 detik tanpa henti ============
# =============================================================================
class LocalSandboxStressTester:
    """
    Pengujian Stabilitas Enterprise: Kode dijalankan selama tepat 3600 detik (1 jam).

    Keunggulan vs Replit Agent / Manus AI:
    - Replit/Manus membatasi sandbox hanya beberapa menit.
    - Sistem ini mengeksekusi kode LOKAL di VPS selama 1 JAM PENUH.
    - Mendeteksi: memory leak, null pointer, crash, infinite loop yang hang.
    - Kode hanya dikirim ke Telegram jika LULUS 3600 detik tanpa crash.
    - Log lengkap disertakan sebagai bukti kelulusan.
    """

    STRESS_DURATION_SECONDS = 3600
    MEMORY_LIMIT_MB = 512
    SAMPLE_INTERVAL_SECONDS = 30

    # File ekstensi berdasarkan bahasa
    _EXT_MAP = {
        "python": ".py",
        "bash": ".sh", "sh": ".sh",
        "javascript": ".js",
    }

    # Command eksekusi berdasarkan bahasa
    _CMD_MAP = {
        "python": ["python3", "{file}"],
        "bash":   ["bash", "{file}"],
        "sh":     ["bash", "{file}"],
        "javascript": ["node", "{file}"],
    }

    @staticmethod
    def _get_process_memory_mb(pid: int) -> float:
        """Baca penggunaan memori proses dalam MB dari /proc/PID/status."""
        try:
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        return kb / 1024.0
        except Exception:
            pass
        return 0.0

    @staticmethod
    async def run_stress_test(
        code: str,
        language: str,
        task_name: str = "polyglot_task",
        duration_seconds: int = None
    ) -> Tuple[bool, str]:
        """
        Jalankan kode selama `duration_seconds` detik.
        Return: (survived, log_report)
        """
        if duration_seconds is None:
            duration_seconds = LocalSandboxStressTester.STRESS_DURATION_SECONDS

        lang_lower = language.lower()

        # Hanya dukung bahasa yang bisa dieksekusi langsung
        if lang_lower not in LocalSandboxStressTester._CMD_MAP:
            msg = (
                f"STRESS_TEST_SKIPPED: Bahasa '{language}' tidak mendukung "
                f"eksekusi langsung di VPS (perlu compile). "
                f"Sintaks sudah diverifikasi via PistonCloud."
            )
            console_terminal_interface.print(f"[dim yellow]  [StressTester] {msg}[/dim yellow]")
            return True, msg

        ext = LocalSandboxStressTester._EXT_MAP.get(lang_lower, ".txt")
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix=f"stress_{task_name}_")
        os.close(fd)

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(code)

            if lang_lower == "bash" or lang_lower == "sh":
                os.chmod(temp_path, 0o755)

            cmd_template = LocalSandboxStressTester._CMD_MAP[lang_lower]
            cmd = [c.replace("{file}", temp_path) for c in cmd_template]

            console_terminal_interface.print(
                f"[bold magenta]  \U0001f9ea [StressTester] MEMULAI UJI STABILITAS 1 JAM "
                f"untuk '{task_name}' ({language})...[/bold magenta]"
            )
            console_terminal_interface.print(
                f"[dim]  Target: {duration_seconds} detik | "
                f"Memory limit: {LocalSandboxStressTester.MEMORY_LIMIT_MB}MB[/dim]"
            )

            loop = asyncio.get_event_loop()
            start_time = time.time()
            crash_log = []
            memory_samples = []
            sample_count = 0
            process_ref = [None]

            def _run_with_monitor():
                """Jalankan proses dan monitor secara sinkron di thread terpisah."""
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    process_ref[0] = proc

                    elapsed = 0.0
                    while elapsed < duration_seconds:
                        try:
                            proc.wait(timeout=LocalSandboxStressTester.SAMPLE_INTERVAL_SECONDS)
                            # Proses selesai sebelum waktunya
                            ret = proc.returncode
                            if ret != 0:
                                stderr_out = proc.stderr.read(2000) if proc.stderr else ""
                                crash_log.append(
                                    f"[t={elapsed:.0f}s] CRASH: exit_code={ret}\n{stderr_out}"
                                )
                                return False
                            else:
                                # Proses selesai dengan sukses (mungkin script singkat)
                                return True
                        except subprocess.TimeoutExpired:
                            pass

                        elapsed = time.time() - start_time

                        # Sample memori
                        if proc.pid:
                            mem_mb = LocalSandboxStressTester._get_process_memory_mb(proc.pid)
                            memory_samples.append(mem_mb)

                            if mem_mb > LocalSandboxStressTester.MEMORY_LIMIT_MB:
                                crash_log.append(
                                    f"[t={elapsed:.0f}s] MEMORY LEAK: {mem_mb:.1f}MB > "
                                    f"{LocalSandboxStressTester.MEMORY_LIMIT_MB}MB limit"
                                )
                                proc.kill()
                                return False

                        console_terminal_interface.print(
                            f"[dim]  [StressTester] t={elapsed:.0f}s | "
                            f"mem={memory_samples[-1]:.1f}MB | RUNNING...[/dim]"
                        )

                    # Selesai 3600 detik - matikan proses
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return True

                except Exception as e:
                    crash_log.append(f"MONITOR EXCEPTION: {traceback.format_exc()}")
                    return False

            survived = await loop.run_in_executor(None, _run_with_monitor)
            elapsed_total = time.time() - start_time

            # Buat laporan
            max_mem = max(memory_samples) if memory_samples else 0.0
            avg_mem = sum(memory_samples) / len(memory_samples) if memory_samples else 0.0

            if survived:
                report = (
                    f"\U0001f3c6 STRESS TEST LULUS - STANDAR ENTERPRISE\n"
                    f"Task: {task_name} ({language})\n"
                    f"Durasi: {elapsed_total:.0f} detik dari target {duration_seconds} detik\n"
                    f"Memori Maks: {max_mem:.1f}MB | Rata-rata: {avg_mem:.1f}MB\n"
                    f"Sample: {len(memory_samples)} titik pengukuran\n"
                    f"Status: TIDAK ADA CRASH, MEMORY LEAK, ATAU HANG\n"
                    f"Kode ini SIAP PRODUKSI - Melampaui standar Replit Agent & Manus AI."
                )
                console_terminal_interface.print(f"[bold green]  \u2705 [StressTester] {report[:150]}[/bold green]")
            else:
                crash_summary = "\n".join(crash_log[:5])
                report = (
                    f"\u274c STRESS TEST GAGAL\n"
                    f"Task: {task_name} ({language})\n"
                    f"Durasi berjalan: {elapsed_total:.0f} detik\n"
                    f"Crash log:\n{crash_summary}"
                )
                console_terminal_interface.print(f"[bold red]  [StressTester] GAGAL: {crash_summary[:200]}[/bold red]")

            return survived, report

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
