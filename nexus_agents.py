import asyncio
import json
import re
import os
import uuid
import shutil
import signal
import subprocess
import requests
import difflib
from typing import Tuple

from nexus_healer import ApexKeyRotator

from nexus_config import (
    console_terminal_interface,
    TEMP_IO_DIRECTORY,
    ACTIVE_AGENTS,
    APIKeyRotator,
    GEMINI_CLI_PATH,
    ROBLOX_MCP_URL,
)
from nexus_database import retrieve_ecosystem_context, save_verified_module
from nexus_compiler import AbsoluteOmniValidator, NativeLuauCompiler

_key_rotator = ApexKeyRotator([a["api_key"] for a in ACTIVE_AGENTS if a["api_key"]])

# === UPGRADE #2: BYPASS ANTRIAN PARALEL ===
# Semaphore ditingkatkan dari 1 ke 3: mengizinkan 3 panggilan gemini-cli
# berjalan BERSAMAAN secara paralel ke 10 API Key yang dirotasi.
# Otak Roblox dan Otak Polyglot tidak akan saling block satu sama lain.
CLI_EXECUTION_SEMAPHORE = asyncio.Semaphore(3)

MARKDOWN_BLOCK = chr(96) * 3


def extract_pure_luau_code(raw_payload: str) -> str:
    """Penghancur Markdown tangguh."""
    if not raw_payload:
        return ""
    code = raw_payload.strip()
    code = re.sub(r'^\s*`{3}[a-zA-Z]*\s*\n*', '', code, flags=re.IGNORECASE)
    code = re.sub(r'\n*\s*`{3}\s*$', '', code)
    return code.strip()


def extract_pure_universal_code(raw_payload: str) -> str:
    """Penghancur Markdown untuk kode universal (Python, C++, dll)."""
    if not raw_payload:
        return ""
    code = raw_payload.strip()
    code = re.sub(r'^\s*`{3}[a-zA-Z]*\s*\n*', '', code, flags=re.IGNORECASE)
    code = re.sub(r'\n*\s*`{3}\s*$', '', code)
    return code.strip()


class RobloxMCPBridge:
    """Jembatan HTTP ke PC Lokal (Roblox Studio MCP)."""

    @staticmethod
    async def execute_tool(tool_name: str, arguments: dict) -> str:
        if not ROBLOX_MCP_URL:
            return "ERROR: ROBLOX_MCP_URL tidak dikonfigurasi."

        payload = {
            "jsonrpc": "2.0",
            "method": tool_name,
            "params": arguments,
            "id": 1
        }

        def _post():
            try:
                res = requests.post(f"{ROBLOX_MCP_URL}/jsonrpc", json=payload, timeout=45)
                if res.status_code == 200:
                    return res.text
                return f"MCP_ERROR: Kode {res.status_code} | Pesan: {res.text}"
            except Exception as e:
                return f"MCP_CONNECTION_FAILED: {str(e)}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _post)


class LuauKnowledgeScraper:
    """Sistem RAG Tingkat Militer Ekstrim - KHUSUS ROBLOX/LUAU."""

    @staticmethod
    def _clean_error_query(raw_error: str) -> str:
        clean_text = re.sub(r'temp_[a-zA-Z0-9_]+\.luau:\d+:\s*', '', raw_error)
        clean_text = re.sub(r'[^\w\s]', ' ', clean_text).strip()
        words = clean_text.split()[:6]
        return " ".join(words)

    @staticmethod
    def _clean_task_query(module_name: str) -> str:
        clean_name = re.sub(r'_\d+$', '', module_name)
        clean_name = clean_name.replace('_', ' ')
        return clean_name

    @staticmethod
    async def search_github_luau(query: str) -> str:
        try:
            encoded_query = query.replace(" ", "+")
            url = f"https://api.github.com/search/code?q={encoded_query}+roblox+pushed:>2024-01-01&per_page=2"

            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "Accept: application/vnd.github.v3+json",
                "-H", "User-Agent: NexusAgent/1.0"
            ]

            github_token = os.getenv("GITHUB_TOKEN", "")
            if github_token:
                command.extend(["-H", f"Authorization: Bearer {github_token}"])

            command.append(url)

            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20))
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                items = data.get("items", [])[:2]
                if items:
                    res = "GITHUB ROBLOX KNOWLEDGE:\n"
                    for item in items:
                        repo_name = item.get('repository', {}).get('full_name', '')
                        file_name = item.get('name', '')
                        res += f"--- FILE: {repo_name}/{file_name} ---\n"
                    return res
        except Exception:
            pass
        return ""

    @staticmethod
    async def search_devforum(query: str) -> str:
        try:
            encoded_query = query.replace(" ", "+")
            url = f"https://devforum.roblox.com/search/query.json?q={encoded_query}"

            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "User-Agent: NexusAgent/1.0",
                url
            ]
            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20))
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                posts = data.get("posts", [])[:2]
                if posts:
                    res = "ROBLOX DEVFORUM SOLUTIONS:\n"
                    for p in posts:
                        res += f"--- POST ID: {p.get('id', 'N/A')} ---\n"
                    return res
        except Exception:
            pass
        return ""

    @staticmethod
    async def search_reddit_robloxdev(query: str) -> str:
        try:
            encoded_query = query.replace(" ", "+")
            url = f"https://www.reddit.com/r/robloxdev/search.json?q={encoded_query}&restrict_sr=1&limit=3"
            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "User-Agent: NexusAgent/1.0",
                url
            ]
            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20))
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                posts = data.get("data", {}).get("children", [])[:3]
                if posts:
                    res = "REDDIT r/robloxdev DISCUSSIONS:\n"
                    for p in posts:
                        post_data = p.get("data", {})
                        title = post_data.get('title', '')
                        res += f"--- DISCUSSION: {title} ---\n"
                    return res
        except Exception:
            pass
        return ""


# =============================================================================
# === UPGRADE #1: DINDING API MEMORI - PolyglotRAGScraper =====================
# =============================================================================
# RAG system EKSKLUSIF untuk kode universal. Tidak pernah menyentuh
# Roblox DevForum, Luau DevForum, atau database ekosistem game apapun.
class PolyglotRAGScraper:
    """
    Sistem RAG Hyper-Aggressive untuk kode UNIVERSAL (Python, C++, Go, Rust, dll).

    DINDING API MEMORI ABSOLUT:
    - Kelas ini TIDAK PERNAH mengakses ekosistem Roblox/Luau.
    - Seluruh pencarian diarahkan ke GitHub SotA 2026, StackOverflow,
      dan forum developer universal.
    """

    @staticmethod
    def _build_universal_query(task_description: str, language: str = "") -> str:
        clean = re.sub(r'[^\w\s]', ' ', task_description)
        words = clean.split()[:8]
        query = " ".join(words)
        if language:
            query = f"{language} {query}"
        return query

    @staticmethod
    async def search_github_universal(query: str, language: str = "") -> str:
        """Cari repository terbaik di GitHub - State-of-the-Art 2026."""
        try:
            encoded_query = query.replace(" ", "+")
            lang_filter = f"+language:{language}" if language else ""
            url = (
                f"https://api.github.com/search/repositories"
                f"?q={encoded_query}{lang_filter}+stars:>50+pushed:>2024-01-01"
                f"&sort=stars&order=desc&per_page=3"
            )
            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "Accept: application/vnd.github.v3+json",
                "-H", "User-Agent: NexusPolyglot/2.0"
            ]
            github_token = os.getenv("GITHUB_TOKEN", "")
            if github_token:
                command.extend(["-H", f"Authorization: Bearer {github_token}"])
            command.append(url)
            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(
                None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20)
            )
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                items = data.get("items", [])[:3]
                if items:
                    res = "GITHUB STATE-OF-THE-ART 2026 REPOS:\n"
                    for item in items:
                        full_name = item.get('full_name', '')
                        description = item.get('description', '')[:80]
                        stars = item.get('stargazers_count', 0)
                        res += f"--- REPO: {full_name} (\u2b50{stars}) | {description} ---\n"
                    return res
        except Exception:
            pass
        return ""

    @staticmethod
    async def search_stackoverflow(query: str, language: str = "") -> str:
        """Cari solusi di StackOverflow - sumber jawaban teknis terpercaya."""
        try:
            encoded_query = query.replace(" ", "+")
            tag_filter = f";{language}" if language else ""
            url = (
                f"https://api.stackexchange.com/2.3/search/advanced"
                f"?order=desc&sort=votes&q={encoded_query}"
                f"&tags=python{tag_filter}&site=stackoverflow&pagesize=2"
            )
            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "User-Agent: NexusPolyglot/2.0",
                url
            ]
            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(
                None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20)
            )
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                items = data.get("items", [])[:2]
                if items:
                    res = "STACKOVERFLOW SOLUTIONS:\n"
                    for item in items:
                        title = item.get('title', '')
                        score = item.get('score', 0)
                        link = item.get('link', '')
                        res += f"--- Q: {title} (score:{score}) | {link} ---\n"
                    return res
        except Exception:
            pass
        return ""

    @staticmethod
    async def search_github_code_examples(query: str, language: str = "") -> str:
        """Cari contoh kode nyata di GitHub."""
        try:
            encoded_query = query.replace(" ", "+")
            lang_filter = f"+language:{language}" if language else ""
            url = (
                f"https://api.github.com/search/code"
                f"?q={encoded_query}{lang_filter}+pushed:>2024-06-01&per_page=2"
            )
            command = [
                "curl", "-s", "--max-time", "15",
                "-H", "Accept: application/vnd.github.v3+json",
                "-H", "User-Agent: NexusPolyglot/2.0"
            ]
            github_token = os.getenv("GITHUB_TOKEN", "")
            if github_token:
                command.extend(["-H", f"Authorization: Bearer {github_token}"])
            command.append(url)
            loop = asyncio.get_event_loop()
            proses = await loop.run_in_executor(
                None, lambda: subprocess.run(command, capture_output=True, text=True, timeout=20)
            )
            if proses.returncode == 0 and proses.stdout:
                data = json.loads(proses.stdout)
                items = data.get("items", [])[:2]
                if items:
                    res = "GITHUB CODE EXAMPLES (SotA 2026):\n"
                    for item in items:
                        repo_name = item.get('repository', {}).get('full_name', '')
                        file_name = item.get('name', '')
                        file_url = item.get('html_url', '')
                        res += f"--- FILE: {repo_name}/{file_name} | {file_url} ---\n"
                    return res
        except Exception:
            pass
        return ""


# =============================================================================
# === EKSEKUTOR INTI - OTAK ROBLOX (tidak diubah) =============================
# =============================================================================
async def execute_gemini_cli_pure(agent: dict, system_instruction: str, prompt_payload: str) -> Tuple[bool, str]:
    """
    EKSEKUTOR untuk OmniSynthesizerAgent (Otak Roblox).
    Output: JSON dengan "luau_code_payload" atau "mcp_tool_call".
    """
    async with CLI_EXECUTION_SEMAPHORE:
        api_key = _key_rotator.get_key()
        if not api_key:
            return False, "API_KEY_KOSONG"

        unique_session_id = uuid.uuid4().hex
        temp_home_dir = os.path.join(TEMP_IO_DIRECTORY, f"gemini_cli_home_{unique_session_id}")

        try:
            os.makedirs(temp_home_dir, exist_ok=True)
            os.makedirs(os.path.join(temp_home_dir, ".gemini"), exist_ok=True)

            prompt_filepath = os.path.join(temp_home_dir, "input_prompt.txt")
            output_filepath = os.path.join(temp_home_dir, "output_response.txt")

            env_vars = os.environ.copy()
            env_vars["GEMINI_API_KEY"] = api_key
            env_vars["CI"] = "true"
            env_vars["TERM"] = "dumb"
            env_vars["NO_COLOR"] = "1"
            env_vars["HOME"] = temp_home_dir

            schema_enforcement = (
                "WAJIB OUTPUT JSON MURNI DENGAN SALAH SATU DARI 2 FORMAT BERIKUT INI:\n\n"
                "PILIHAN 1: JIKA INGIN MEMANGGIL MCP TOOL:\n"
                '{"mcp_tool_call": {"tool_name": "start_playtest", "args": {}}}\n\n'
                "PILIHAN 2: JIKA SUDAH SELESAI DAN INGIN MEMBERIKAN KODE LUAU FINAL:\n"
                '{"luau_code_payload": "string kode luau murni"}'
            )

            full_payload = (
                f"[SYSTEM INSTRUCTION]:\n{system_instruction}\n\n"
                f"[WAJIB OUTPUT JSON MURNI]:\n{schema_enforcement}\n\n"
                f"[PROMPT TASK]:\n{prompt_payload}"
            )

            with open(prompt_filepath, "w", encoding="utf-8") as f:
                f.write(full_payload)

            model_candidates = [
                "models/gemini-2.5-flash",
                "models/gemini-2.0-flash",
                "models/gemini-1.5-flash",
            ]

            last_error = ""
            for model_name in model_candidates:
                try:
                    with open(prompt_filepath, "r", encoding="utf-8") as f:
                        prompt_content = f.read()

                    command = [
                        GEMINI_CLI_PATH,
                        "-m", model_name,
                        "-y",
                        "--temp", "1.0",
                        "--top-p", "0.95",
                        "--top-k", "64",
                        "-p", "Baca seluruh data instruksi dari stdin. Keluarkan JSON murni.",
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env_vars,
                        start_new_session=True,
                    )

                    try:
                        stdout_data, stderr_data = await asyncio.wait_for(
                            process.communicate(input=prompt_content.encode("utf-8")),
                            timeout=1800.0,
                        )
                    except asyncio.TimeoutError:
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except (OSError, ProcessLookupError):
                            pass
                        try:
                            await asyncio.wait_for(process.communicate(), timeout=5.0)
                        except asyncio.TimeoutError:
                            pass
                        last_error = f"API Timeout 1800s ({model_name})."
                        continue

                    if process.returncode != 0:
                        error_details = stderr_data.decode("utf-8", errors="ignore").strip().lower()
                        if "429" in error_details or "quota" in error_details or "exhausted" in error_details or "rate" in error_details:
                            _key_rotator.mark_rate_limited(api_key)
                            return False, "RATE_LIMIT_REACHED"
                        last_error = f"CLI_ERROR ({model_name}): {error_details[:300]}"
                        continue

                    raw_output = stdout_data.decode("utf-8", errors="ignore")

                    with open(output_filepath, "w", encoding="utf-8") as f:
                        f.write(raw_output)

                    json_str = ""
                    markdown_match = re.search(f'{MARKDOWN_BLOCK}(?:json)?\n(.*?)\n{MARKDOWN_BLOCK}', raw_output, re.DOTALL | re.IGNORECASE)
                    if markdown_match:
                        json_str = markdown_match.group(1).strip()
                    else:
                        start_idx = raw_output.find('{')
                        end_idx = raw_output.rfind('}')
                        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                            json_str = raw_output[start_idx:end_idx + 1]

                    if json_str:
                        try:
                            parsed = json.loads(json_str, strict=False)
                            if "luau_code_payload" in parsed:
                                code = parsed["luau_code_payload"]
                                if code:
                                    return True, extract_pure_luau_code(code)
                            elif "mcp_tool_call" in parsed:
                                return True, json.dumps(parsed)
                        except Exception:
                            pass

                    last_error = f"JSON_PARSE_ERROR ({model_name}): Output rusak atau tidak sesuai skema.\nRaw: {raw_output[:200]}..."
                    continue

                except FileNotFoundError:
                    return False, f"GEMINI_CLI_NOT_FOUND: CLI tidak ditemukan di {GEMINI_CLI_PATH}"
                except Exception as e:
                    last_error = f"SYSTEM_EXCEPTION ({model_name}): {str(e)}"
                    continue

            return False, last_error

        finally:
            if os.path.exists(temp_home_dir):
                shutil.rmtree(temp_home_dir, ignore_errors=True)


# =============================================================================
# === UPGRADE #1 & #2: EKSEKUTOR EKSKLUSIF OTAK POLYGLOT =====================
# =============================================================================
async def execute_gemini_cli_polyglot(
    agent: dict, system_instruction: str, prompt_payload: str
) -> Tuple[bool, str, str]:
    """
    EKSEKUTOR TERPISAH untuk PolyglotSynthesizerAgent (Otak Universal).

    DINDING API MEMORI: Tidak menerima/mengirim konteks Roblox/Luau apapun.
    Output schema berbeda: {"language": "python", "code_payload": "..."}
    Return: (success, code_string, language_string)
    """
    async with CLI_EXECUTION_SEMAPHORE:
        api_key = _key_rotator.get_key()
        if not api_key:
            return False, "API_KEY_KOSONG", ""

        unique_session_id = uuid.uuid4().hex
        temp_home_dir = os.path.join(TEMP_IO_DIRECTORY, f"polyglot_cli_{unique_session_id}")

        try:
            os.makedirs(temp_home_dir, exist_ok=True)
            os.makedirs(os.path.join(temp_home_dir, ".gemini"), exist_ok=True)

            prompt_filepath = os.path.join(temp_home_dir, "poly_input.txt")
            output_filepath = os.path.join(temp_home_dir, "poly_output.txt")

            env_vars = os.environ.copy()
            env_vars["GEMINI_API_KEY"] = api_key
            env_vars["CI"] = "true"
            env_vars["TERM"] = "dumb"
            env_vars["NO_COLOR"] = "1"
            env_vars["HOME"] = temp_home_dir

            schema_enforcement = (
                "WAJIB OUTPUT JSON MURNI DENGAN FORMAT BERIKUT:\n\n"
                '{"language": "python", "code_payload": "string kode lengkap dan siap jalan"}\n\n'
                "Nilai 'language' yang valid: python, cpp, go, rust, javascript, typescript, java, bash, dll.\n"
                "JANGAN tulis penjelasan di luar JSON. HANYA JSON MURNI."
            )

            full_payload = (
                f"[SYSTEM INSTRUCTION]:\n{system_instruction}\n\n"
                f"[WAJIB OUTPUT JSON MURNI]:\n{schema_enforcement}\n\n"
                f"[PROMPT TASK]:\n{prompt_payload}"
            )

            with open(prompt_filepath, "w", encoding="utf-8") as f:
                f.write(full_payload)

            model_candidates = [
                "models/gemini-2.5-flash",
                "models/gemini-2.0-flash",
                "models/gemini-1.5-flash",
            ]

            last_error = ""
            for model_name in model_candidates:
                try:
                    with open(prompt_filepath, "r", encoding="utf-8") as f:
                        prompt_content = f.read()

                    command = [
                        GEMINI_CLI_PATH,
                        "-m", model_name,
                        "-y",
                        "--temp", "1.0",
                        "--top-p", "0.95",
                        "--top-k", "64",
                        "-p", "Baca instruksi dari stdin. REASON LONGER. Berpikirlah mendalam. JSON murni saja.",
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env_vars,
                        start_new_session=True,
                    )

                    try:
                        stdout_data, stderr_data = await asyncio.wait_for(
                            process.communicate(input=prompt_content.encode("utf-8")),
                            timeout=1800.0,
                        )
                    except asyncio.TimeoutError:
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except (OSError, ProcessLookupError):
                            pass
                        try:
                            await asyncio.wait_for(process.communicate(), timeout=5.0)
                        except asyncio.TimeoutError:
                            pass
                        last_error = f"POLYGLOT Timeout 1800s ({model_name})."
                        continue

                    if process.returncode != 0:
                        error_details = stderr_data.decode("utf-8", errors="ignore").strip().lower()
                        if "429" in error_details or "quota" in error_details or "exhausted" in error_details or "rate" in error_details:
                            _key_rotator.mark_rate_limited(api_key)
                            return False, "RATE_LIMIT_REACHED", ""
                        last_error = f"POLYGLOT CLI_ERROR ({model_name}): {error_details[:300]}"
                        continue

                    raw_output = stdout_data.decode("utf-8", errors="ignore")

                    with open(output_filepath, "w", encoding="utf-8") as f:
                        f.write(raw_output)

                    json_str = ""
                    markdown_match = re.search(
                        f'{MARKDOWN_BLOCK}(?:json)?\n(.*?)\n{MARKDOWN_BLOCK}',
                        raw_output, re.DOTALL | re.IGNORECASE
                    )
                    if markdown_match:
                        json_str = markdown_match.group(1).strip()
                    else:
                        start_idx = raw_output.find('{')
                        end_idx = raw_output.rfind('}')
                        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                            json_str = raw_output[start_idx:end_idx + 1]

                    if json_str:
                        try:
                            parsed = json.loads(json_str, strict=False)
                            if "code_payload" in parsed:
                                code = parsed["code_payload"]
                                language = parsed.get("language", "python")
                                if code:
                                    return True, extract_pure_universal_code(code), language
                        except Exception:
                            pass

                    last_error = f"POLYGLOT JSON_PARSE_ERROR ({model_name}): Output tidak sesuai skema.\nRaw: {raw_output[:200]}..."
                    continue

                except FileNotFoundError:
                    return False, f"GEMINI_CLI_NOT_FOUND: {GEMINI_CLI_PATH}", ""
                except Exception as e:
                    last_error = f"POLYGLOT SYSTEM_EXCEPTION ({model_name}): {str(e)}"
                    continue

            return False, last_error, ""

        finally:
            if os.path.exists(temp_home_dir):
                shutil.rmtree(temp_home_dir, ignore_errors=True)


class AutoHealerAgent:
    def __init__(self):
        self.sys_inst = (
            "BERPIKIRLAH SECARA MENDALAM DAN EKSTENSIF SEBELUM MENJAWAB! "
            "Anda adalah Ahli Bedah Kode Level Master dengan standar militer. "
            "TUGAS MUTLAK: Perbaiki kode Luau yang rusak berdasarkan error dari compiler. "
            "Terapkan pengujian tingkat militer sehingga kode perbaikan Anda 99% tidak mungkin eror."
        )
        self.heal_history = {}

    def _analyze_error_type(self, error_msg: str) -> str:
        error_lower = error_msg.lower()
        if "but got" in error_lower or "expected" in error_lower:
            return "TYPE_MISMATCH"
        elif "unknown" in error_lower and ("global" in error_lower or "type" in error_lower):
            return "UNDEFINED_REFERENCE"
        elif "syntax" in error_lower or "unexpected symbol" in error_lower:
            return "SYNTAX_ERROR"
        elif "cannot assign" in error_lower or "function only returns" in error_lower:
            return "ASSIGNMENT_ERROR"
        elif "unknown property" in error_lower or "not found" in error_lower:
            return "PROPERTY_ERROR"
        else:
            return "GENERIC_ERROR"

    def _generate_fix_guidance(self, error_msg: str, error_type: str) -> str:
        base_searching = "WAJIB SEARCHING SEBELUM FIX:\n- Cari solusi serupa di referensi Roblox DevForum\n\n"
        guidance = {
            "TYPE_MISMATCH": base_searching + "- Tambahkan type casting: `x as Y` atau `tostring()`.",
            "UNDEFINED_REFERENCE": base_searching + "- Cek: apakah sudah di-require? apakah ada typo?",
            "SYNTAX_ERROR": base_searching + "- Luau strict mode: semua variable harus declared dengan local/const.",
            "ASSIGNMENT_ERROR": base_searching + "- Fix: gunakan temp variable, atau ubah type target.",
            "PROPERTY_ERROR": base_searching + "- Untuk Roblox Instance: gunakan GetChildren(), FindFirstChild() dengan benar.",
            "GENERIC_ERROR": base_searching + "- Bacalah error message dengan teliti, cari highlight line number.",
        }
        return guidance.get(error_type, guidance["GENERIC_ERROR"])

    async def heal_code(
        self,
        broken_code: str,
        compiler_error: str,
        module_name: str,
        agent: dict,
        task_description: str = "",
        ecosystem_context: str = "",
        previous_error: str = "",
        target_filepath: str = ""
    ) -> str:
        last_error_line = compiler_error.splitlines()[-1] if compiler_error else "Unknown"
        error_type = self._analyze_error_type(compiler_error)

        if module_name not in self.heal_history:
            self.heal_history[module_name] = []
        self.heal_history[module_name].append(error_type)

        console_terminal_interface.print(f"[bold magenta]   [Auto-Healer] Membedah {module_name} ({error_type}): {last_error_line}[/bold magenta]")

        safe_broken_code = extract_pure_luau_code(broken_code)
        fix_guidance = self._generate_fix_guidance(compiler_error, error_type)

        base_prompt = (
            f"[ERROR CLASSIFICATION]: {error_type}\n"
            f"[ERROR MESSAGE COMPILER LUNE/ROJO]:\n{compiler_error}\n\n"
            f"[RECOMMENDED FIX STRATEGY]:\n{fix_guidance}\n\n"
        )
        if ecosystem_context:
            base_prompt += f"[MODUL ECOSYSTEM REFERENCE]:\n{ecosystem_context}\n\n"

        clean_error_q = LuauKnowledgeScraper._clean_error_query(compiler_error)
        clean_task_name = LuauKnowledgeScraper._clean_task_query(module_name)
        combined_query = f"{clean_task_name} {clean_error_q}"[:80]

        github_context = await LuauKnowledgeScraper.search_github_luau(combined_query)
        devforum_context = await LuauKnowledgeScraper.search_devforum(combined_query)
        reddit_context = await LuauKnowledgeScraper.search_reddit_robloxdev(combined_query)

        if github_context or devforum_context or reddit_context:
            base_prompt += "[KNOWLEDGE BASE]\n"
            if github_context:
                base_prompt += github_context + "\n"
            if devforum_context:
                base_prompt += devforum_context + "\n"
            if reddit_context:
                base_prompt += reddit_context + "\n"

        base_prompt += (
            f"[KODE YANG RUSAK]:\n{MARKDOWN_BLOCK}lua\n{safe_broken_code}\n{MARKDOWN_BLOCK}\n\n"
            f"[INSTRUKSI BEDAH MUTLAK]:\n"
            f"1. Identifikasi EXACT baris penyebab error.\n"
            f"2. Pahami root cause dari error type '{error_type}'.\n"
            f"3. Ubah HANYA baris yang rusak.\n"
            f"4. Wajib mengembalikan file utuh setelah diperbaiki.\n"
        )

        mcp_history_log = ""
        max_mcp_turns = 4 if ROBLOX_MCP_URL else 1

        for turn in range(max_mcp_turns):
            dynamic_prompt = base_prompt
            if mcp_history_log:
                dynamic_prompt += f"\n\n[RIWAYAT MCP TOOL EXECUTION]:\n{mcp_history_log}"

            success, result_data = await execute_gemini_cli_pure(agent, self.sys_inst, dynamic_prompt)

            if not success:
                console_terminal_interface.print(f"[bold red]   [Healer Error] {result_data[:200]}[/bold red]")
                return broken_code

            if '"mcp_tool_call"' in result_data:
                try:
                    tool_data = json.loads(result_data)["mcp_tool_call"]
                    tool_name = tool_data.get("tool_name", "unknown")
                    tool_args = tool_data.get("args", {})

                    console_terminal_interface.print(f"[bold cyan]   \U0001f6e0\ufe0f [MCP Action] AI Menjalankan Studio Tool: {tool_name}[/bold cyan]")

                    tool_response = await RobloxMCPBridge.execute_tool(tool_name, tool_args)
                    mcp_history_log += f"\n--- CALL: {tool_name} ---\nRESULT: {tool_response[:1000]}\n"
                    continue
                except Exception as e:
                    mcp_history_log += f"\n--- CALL FAILED ---\nERROR: {str(e)}\n"
                    continue
            else:
                return extract_pure_luau_code(result_data)

        return broken_code


# =============================================================================
# === OTAK #1: OmniSynthesizerAgent (Roblox/Luau - tidak diubah logikanya) ====
# =============================================================================
class OmniSynthesizerAgent:
    """
    OTAK #1: Spesialis eksklusif Roblox/Luau.
    DINDING API MEMORI: Satu-satunya agen yang boleh memanggil
    retrieve_ecosystem_context() untuk membaca kode Luau sebelumnya.
    """
    def __init__(self, healer_agent: AutoHealerAgent):
        self.healer_agent = healer_agent
        self.sys_inst = (
            "BERPIKIRLAH SECARA MENDALAM DAN EKSTENSIF SEBELUM MENJAWAB! "
            "Anda adalah Arsitek Penyatuan Multiverse Luau tingkat militer. Tulis kode Luau Murni. "
            "PROTOKOL MUTLAK: Wajib menganalisis kode sebelum diberikan. "
            "Kode yang dibuat harus 99% tidak mungkin eror. "
            "Wajib --!strict. Fokus pada efisiensi matematika dan pencegahan memory leak."
        )

    async def synthesize_handoff(
        self,
        agent: dict,
        target_filepath: str,
        module_name: str,
        task_description: str,
        req_keys: list,
        forb_keys: list,
        previous_error: str,
        previous_code: str,
    ) -> Tuple[bool, str, str]:
        comprehensive_prompt = (
            f"[KEYWORD WAJIB]: {', '.join(req_keys) if req_keys else 'Tidak ada keyword khusus'}\n"
            f"[KEYWORD HARAM]: {', '.join(forb_keys) if forb_keys else 'Tidak ada batasan khusus'}\n\n"
            f"[CHEAT SHEET KEAMANAN MILITER]\n"
            f"01. Baris pertama WAJIB `--!strict`.\n"
            f"02. HARAM: `_G`, `shared`, `loadstring`, `getfenv`, `spawn()`, `delay()`.\n"
            f"03. Loop `while true do` WAJIB gunakan `task.wait()` atau RunService.\n"
            f"04. ANTI-MEMORY LEAK: Setiap koneksi event WAJIB disimpan ke variabel.\n"
            f"05. FAULT-TOLERANCE: Operasi DataStore WAJIB dibungkus `pcall()`.\n"
            f"06. ZERO-TRUST: OnServerEvent WAJIB validasi dengan `typeof()`.\n\n"
            f"[HUKUM GAME ALAM SEMESTA]\n"
            f"1. Game Ekstraksi Survival. Sudut pandang First-Person.\n"
            f"2. Pisahkan LOBBY dan DUNIA FANTASI secara fisik dan logis.\n"
            f"3. Raw material HARAM punya Recipe/Durability/ArmorTier.\n"
            f"4. Senjata modern tembakan Raycast, TIDAK BOLEH punya Damage variable.\n"
            f"5. Armor WAJIB punya ArmorTier (1-6), Durability, MaterialType.\n\n"
        )

        # DINDING API MEMORI: Hanya OmniSynthesizerAgent yang WAJIB membaca
        # database ekosistem Roblox. PolyglotSynthesizerAgent TIDAK PERNAH ke sini.
        ecosystem_context = await retrieve_ecosystem_context()
        if ecosystem_context:
            comprehensive_prompt += f"[REFERENSI MODUL GLOBAL]:\n{ecosystem_context}\n\n"
        comprehensive_prompt += f"[INSTRUKSI TUGAS ({module_name})]:\n{task_description}\n\n"

        if previous_error and previous_code:
            safe_code = extract_pure_luau_code(previous_code)
            comprehensive_prompt += (
                f"[CRITICAL ERROR DARI AGEN SEBELUMNYA]:\n"
                f"{MARKDOWN_BLOCK}lua\n{safe_code}\n{MARKDOWN_BLOCK}\n"
                f"[ERROR LOG]:\n{previous_error}\n\n"
                "[HUKUM PERBAIKAN]:\n"
                "1. Dilarang merombak bagian kode yang sudah BENAR.\n"
                "2. Jika gagal di banyak titik, rombak bagian yang rusak secara masif.\n"
                "3. Berikan kode utuh yang siap jalan.\n"
            )

        console_terminal_interface.print(
            f"[bold cyan]  [{agent['name']}] [OTAK ROBLOX] Memproses {module_name}... (Parallel Queue)[/bold cyan]"
        )

        clean_task_query = LuauKnowledgeScraper._clean_task_query(module_name)
        github_context = await LuauKnowledgeScraper.search_github_luau(clean_task_query)
        devforum_context = await LuauKnowledgeScraper.search_devforum(clean_task_query)
        reddit_context = await LuauKnowledgeScraper.search_reddit_robloxdev(clean_task_query)

        if github_context or devforum_context or reddit_context:
            live_rag_data = "[KNOWLEDGE BASE (SCRAPING GITHUB, DEVFORUM & REDDIT)]\n"
            if github_context:
                live_rag_data += github_context + "\n"
            if devforum_context:
                live_rag_data += devforum_context + "\n"
            if reddit_context:
                live_rag_data += reddit_context + "\n"
            comprehensive_prompt += live_rag_data

        success, result_data = await execute_gemini_cli_pure(agent, self.sys_inst, comprehensive_prompt)

        if success:
            code_attempt = result_data
            if '"mcp_tool_call"' in code_attempt:
                return False, "Agent Error: Synthesizer tidak boleh memanggil Tool MCP.", previous_code

            if previous_code and previous_error:
                safe_prev_code = extract_pure_luau_code(previous_code)
                similarity = difflib.SequenceMatcher(None, safe_prev_code, code_attempt).ratio()

                if similarity < 0.15 and len(code_attempt) < 200:
                    console_terminal_interface.print(f"[bold red]  [SANITY CHECK GAGAL]: Kode baru terlalu pendek atau berbeda drastis. DITOLAK.[/bold red]")
                    return False, "SANITY_CHECK_FAIL: Kode kosong/tidak valid", previous_code

            omni_valid, omni_msg = AbsoluteOmniValidator.execute_validation(code_attempt, req_keys, forb_keys)
            if not omni_valid:
                console_terminal_interface.print(f"[bold red]  [OmniValidator GAGAL]: {omni_msg[:300]}[/bold red]")
                healed_code = await self.healer_agent.heal_code(
                    code_attempt, omni_msg, module_name, agent, task_description, ecosystem_context,
                    target_filepath=target_filepath
                )
                omni_valid2, omni_msg2 = AbsoluteOmniValidator.execute_validation(healed_code, req_keys, forb_keys)
                if not omni_valid2:
                    return False, omni_msg2, healed_code

                ast_ok, ast_msg = await NativeLuauCompiler.execute_native_ast_verification(healed_code, module_name)
                if not ast_ok:
                    return False, ast_msg, healed_code

                os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
                with open(target_filepath, "w", encoding="utf-8") as f:
                    f.write(healed_code)
                await save_verified_module(module_name, target_filepath, healed_code)
                console_terminal_interface.print(f"[bold green]  \u2705 {module_name} LULUS setelah Healer bedah![/bold green]")
                return True, "", healed_code

            ast_ok, ast_msg = await NativeLuauCompiler.execute_native_ast_verification(code_attempt, module_name)
            if not ast_ok:
                console_terminal_interface.print(f"[bold red]  [AST FAILED]: {ast_msg[:300]}[/bold red]")
                healed_code = await self.healer_agent.heal_code(
                    code_attempt, ast_msg, module_name, agent, task_description, ecosystem_context,
                    target_filepath=target_filepath
                )
                omni_valid2, omni_msg2 = AbsoluteOmniValidator.execute_validation(healed_code, req_keys, forb_keys)
                if not omni_valid2:
                    return False, omni_msg2, healed_code

                ast_ok2, ast_msg2 = await NativeLuauCompiler.execute_native_ast_verification(healed_code, module_name)
                if not ast_ok2:
                    return False, ast_msg2, healed_code

                os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
                with open(target_filepath, "w", encoding="utf-8") as f:
                    f.write(healed_code)
                await save_verified_module(module_name, target_filepath, healed_code)
                console_terminal_interface.print(f"[bold green]  \u2705 {module_name} LULUS setelah Healer bedah![/bold green]")
                return True, "", healed_code

            os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
            with open(target_filepath, "w", encoding="utf-8") as f:
                f.write(code_attempt)
            await save_verified_module(module_name, target_filepath, code_attempt)
            console_terminal_interface.print(f"[bold green]  \u2705 {module_name} LULUS! Disimpan ke {target_filepath}[/bold green]")
            return True, "", code_attempt

        console_terminal_interface.print(f"[bold red]  [CLI FAILED]: {result_data[:300]}[/bold red]")
        return False, result_data, previous_code


# =============================================================================
# === UPGRADE #1: OTAK #2 - PolyglotSynthesizerAgent ==========================
# =============================================================================
class PolyglotSynthesizerAgent:
    """
    OTAK #2: Insinyur Senior Poliglot untuk kode UNIVERSAL.

    HUKUM BESI (TIDAK BOLEH DILANGGAR):
    1. TIDAK PERNAH memanggil retrieve_ecosystem_context() - DIPOTONG TOTAL.
    2. TIDAK PERNAH menyebut Roblox, Luau, atau konteks game apapun.
    3. Hanya mengandalkan PolyglotRAGScraper (GitHub SotA 2026 + StackOverflow).
    4. Kode diuji oleh PistonCloudCompiler (sintaks) + LocalSandboxStressTester (1 jam).
    5. Hasil hanya dikirim ke Telegram setelah LULUS stress test penuh.

    UPGRADE #5 - DOKTRIN HYPER-AGGRESSIVE RAG & REASON LONGER:
    - temp=1.0, AI mencetak ribuan token pemikiran sebelum menulis kode.
    - "JANGAN MEREPOTKAN PENGGUNA. Cari sendiri secara agresif di GitHub."
    - "BATCH seluruh pertanyaan jika jalan buntu - jangan tanya user."
    """

    def __init__(self):
        self.sys_inst = (
            "BERPIKIRLAH SECARA MENDALAM DAN LAMA (REASON LONGER) SEBELUM MENULIS KODE! "
            "Anda adalah Insinyur Senior Poliglot Level Staff Engineer yang menguasai "
            "Python, C++, Go, Rust, JavaScript, TypeScript, Java, Bash, dan semua bahasa pemrograman modern. "
            "\n\nDOKTRIN WAJIB:\n"
            "1. JANGAN MEREPOTKAN PENGGUNA. Cari sendiri secara agresif di GitHub (State-of-the-Art 2026).\n"
            "2. BATCH seluruh pertanyaan menjadi riset mandiri jika jalan buntu.\n"
            "3. Gunakan pattern arsitektur terbaik 2026: async-first, zero-copy, memory-safe.\n"
            "4. Kode WAJIB production-ready: error handling lengkap, logging, type hints.\n"
            "5. ANTI-MEMORY LEAK: Gunakan context managers, RAII pattern, weak references.\n"
            "6. ANTI-NULL POINTER: Validasi semua input, gunakan Optional/Result pattern.\n"
            "7. Tulis kode yang bisa bertahan dijalankan 3600 detik tanpa crash.\n"
        )

    def _detect_language(self, task_description: str) -> str:
        task_lower = task_description.lower()
        if any(k in task_lower for k in ["python", ".py", "pip", "django", "flask", "fastapi"]):
            return "python"
        elif any(k in task_lower for k in ["c++", "cpp", "g++", "cmake"]):
            return "cpp"
        elif any(k in task_lower for k in ["golang", " go ", "goroutine", "go module"]):
            return "go"
        elif any(k in task_lower for k in ["rust", "cargo", "tokio"]):
            return "rust"
        elif any(k in task_lower for k in ["javascript", "nodejs", "node.js", "npm"]):
            return "javascript"
        elif any(k in task_lower for k in ["typescript", " ts ", "deno"]):
            return "typescript"
        elif any(k in task_lower for k in ["java ", "maven", "gradle", "spring"]):
            return "java"
        elif any(k in task_lower for k in ["bash", "shell", "sh script", ".sh"]):
            return "bash"
        return "python"

    async def synthesize_universal_code(
        self,
        agent: dict,
        task_description: str,
        task_name: str = "polyglot_task",
        previous_error: str = "",
        previous_code: str = "",
    ) -> Tuple[bool, str, str, str]:
        """
        Sintesis kode universal.
        Return: (success, code, language, error_msg)

        ABSOLUTE CONTEXT ISOLATION:
        retrieve_ecosystem_context() TIDAK DIPANGGIL DI SINI - kanvas bersih murni.
        """
        detected_language = self._detect_language(task_description)

        console_terminal_interface.print(
            f"[bold yellow]  [{agent['name']}] [OTAK POLYGLOT] Memproses '{task_name}' "
            f"bahasa={detected_language} (Parallel Queue)...[/bold yellow]"
        )

        # UPGRADE #5: HYPER-AGGRESSIVE RAG dari GitHub & StackOverflow
        # Bukan dari Roblox DevForum atau Reddit r/robloxdev
        query = PolyglotRAGScraper._build_universal_query(task_description, detected_language)
        github_repos = await PolyglotRAGScraper.search_github_universal(query, detected_language)
        stackoverflow_ctx = await PolyglotRAGScraper.search_stackoverflow(query, detected_language)
        github_examples = await PolyglotRAGScraper.search_github_code_examples(query, detected_language)

        comprehensive_prompt = (
            f"[BAHASA TARGET]: {detected_language.upper()}\n"
            f"[NAMA TUGAS]: {task_name}\n\n"
            f"[STANDAR KODE ENTERPRISE LEVEL]\n"
            f"1. Production-ready: error handling lengkap di setiap fungsi.\n"
            f"2. Type annotations/hints wajib di semua fungsi dan variabel.\n"
            f"3. Logging informatif: gunakan logging module, bukan print().\n"
            f"4. Memory-safe: tidak ada memory leak, resource harus ditutup.\n"
            f"5. Thread-safe jika menggunakan concurrency.\n"
            f"6. Kode harus survive berjalan 3600 detik tanpa crash atau hang.\n\n"
        )

        if github_repos or stackoverflow_ctx or github_examples:
            comprehensive_prompt += "[HYPER-AGGRESSIVE RAG - GITHUB SotA 2026 & STACKOVERFLOW]\n"
            if github_repos:
                comprehensive_prompt += github_repos + "\n"
            if github_examples:
                comprehensive_prompt += github_examples + "\n"
            if stackoverflow_ctx:
                comprehensive_prompt += stackoverflow_ctx + "\n"
            comprehensive_prompt += "\n"

        comprehensive_prompt += f"[INSTRUKSI TUGAS]:\n{task_description}\n\n"

        if previous_error and previous_code:
            comprehensive_prompt += (
                f"[KODE SEBELUMNYA YANG GAGAL]:\n"
                f"{MARKDOWN_BLOCK}{detected_language}\n{previous_code}\n{MARKDOWN_BLOCK}\n"
                f"[ERROR LOG]:\n{previous_error}\n\n"
                "[HUKUM PERBAIKAN]:\n"
                "1. Identifikasi root cause error dengan presisi bedah.\n"
                "2. Ubah hanya bagian yang rusak, jangan merombak yang sudah benar.\n"
                "3. Berikan kode utuh dan siap jalan.\n"
            )

        success, code, language = await execute_gemini_cli_polyglot(agent, self.sys_inst, comprehensive_prompt)

        if success and code:
            console_terminal_interface.print(
                f"[bold green]  \u2705 [OTAK POLYGLOT] {task_name} berhasil "
                f"({language}, {len(code)} chars).[/bold green]"
            )
            return True, code, language, ""

        console_terminal_interface.print(
            f"[bold red]  [OTAK POLYGLOT GAGAL]: {code[:200]}[/bold red]"
        )
        return False, previous_code, detected_language, code
