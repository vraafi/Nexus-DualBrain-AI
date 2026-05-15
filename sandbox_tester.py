import logging
import time
import subprocess
import os
import sys
import tempfile
import shutil


class SandboxTester:
    def __init__(self, duration_minutes=15, llm_client=None):
        self.duration = duration_minutes * 60
        self.llm = llm_client

    def _static_analysis(self, code_path):
        """Runs flake8 to catch syntax errors before executing."""
        logging.info("Running static analysis via flake8...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flake8", code_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                logging.warning(f"Static analysis found potential issues:\n{result.stdout}")
                return False, result.stdout
            return True, ""
        except Exception as e:
            logging.error(f"Failed to run static analysis: {e}")
            return True, ""

    def _search_error(self, error_message):
        """Mencari solusi untuk error sandbox — DuckDuckGo sebagai primary, Gemini sebagai fallback."""
        logging.info(f"Mencari solusi untuk error: {error_message[:100]}...")
        try:
            result = self._search_duckduckgo(f"Python error fix: {error_message}")
            if result:
                return result
        except Exception as e:
            logging.warning(f"DuckDuckGo search gagal: {e}")

        try:
            if self.llm:
                return self.llm._search_web_safe(f"Python error fix for: {error_message}")
        except Exception as e:
            logging.error(f"Gemini search fallback gagal: {e}")

        return ""

    def _search_duckduckgo(self, query):
        """Cari solusi error menggunakan DuckDuckGo (tidak butuh API key)."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            if results:
                snippets = [r.get("body", "") for r in results if r.get("body")]
                return "\n\n".join(snippets[:3])
            return ""
        except ImportError:
            logging.warning("duckduckgo_search tidak terinstall. Skip DDG search.")
            return ""
        except Exception as e:
            logging.warning(f"DuckDuckGo search error: {e}")
            return ""

    def _run_with_llm_sandbox(self, code_path, timeout=300):
        """
        Jalankan kode menggunakan llm-sandbox dengan Docker backend.
        Ini adalah metode utama yang menggunakan library llm-sandbox (github.com/vndee/llm-sandbox).

        Backend yang valid: 'docker', 'kubernetes', 'podman', 'micromamba'
        PENTING: backend='local' TIDAK ADA di llm-sandbox — menyebabkan UnsupportedBackendError.
        """
        from llm_sandbox import SandboxSession, SandboxBackend

        abs_code_path = os.path.abspath(code_path)
        with open(abs_code_path, "r") as f:
            code_to_run = f.read()

        with SandboxSession(
            lang="python",
            backend=SandboxBackend.DOCKER,
            verbose=False
        ) as session:
            result = session.run(
                code=code_to_run,
                libraries=["requests", "beautifulsoup4", "pytest"]
            )

        # Filter stderr: abaikan warning yang tidak kritis
        critical_stderr = ""
        if result.stderr and result.stderr.strip():
            critical_lines = [
                line for line in result.stderr.strip().splitlines()
                if not any(w in line.lower() for w in [
                    "deprecat", "futurewarning", "userwarning",
                    "resourcewarning", "pendingdeprecation"
                ])
            ]
            critical_stderr = "\n".join(critical_lines).strip()

        if critical_stderr:
            raise Exception(f"Execution Failed:\n{critical_stderr}")

        return result.stdout or ""

    def _run_code_subprocess(self, code_path, timeout=300):
        """
        Fallback: jalankan kode Python via subprocess langsung.
        Digunakan jika Docker tidak tersedia atau llm-sandbox gagal.
        """
        abs_code_path = os.path.abspath(code_path)
        work_dir = tempfile.mkdtemp(prefix="nexus_sandbox_")

        try:
            script_name = os.path.basename(abs_code_path)
            dest_path = os.path.join(work_dir, script_name)
            shutil.copy2(abs_code_path, dest_path)

            result = subprocess.run(
                [sys.executable, dest_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir,
                env={**os.environ, "PYTHONPATH": os.getcwd()}
            )

            # Filter stderr
            critical_stderr = ""
            if result.stderr and result.stderr.strip():
                critical_lines = [
                    line for line in result.stderr.strip().splitlines()
                    if not any(w in line.lower() for w in [
                        "deprecat", "futurewarning", "userwarning",
                        "resourcewarning", "pendingdeprecation"
                    ])
                ]
                critical_stderr = "\n".join(critical_lines).strip()

            if result.returncode != 0 and critical_stderr:
                raise Exception(f"Execution Failed (exit {result.returncode}):\n{critical_stderr}")

            return result.stdout or ""

        except subprocess.TimeoutExpired:
            raise Exception(f"Execution timed out setelah {timeout}s")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _execute_code(self, code_path):
        """
        Strategi eksekusi bertingkat:
        1. llm-sandbox dengan Docker backend (primary — sandbox terisolasi)
        2. subprocess langsung (fallback — jika Docker tidak berjalan)
        """
        timeout_sec = min(self.duration, 300)

        # Primary: llm-sandbox + Docker
        try:
            stdout = self._run_with_llm_sandbox(code_path, timeout=timeout_sec)
            logging.info("llm-sandbox (Docker) berhasil. Output: %s", stdout[:200])
            return stdout
        except ImportError:
            logging.warning("llm-sandbox tidak terinstall. Fallback ke subprocess.")
        except Exception as e:
            err_str = str(e)
            # Jika Docker tidak berjalan atau tidak tersedia, langsung fallback
            if any(kw in err_str.lower() for kw in [
                "docker", "connection", "daemon", "socket", "unsupported backend"
            ]):
                logging.warning(
                    "llm-sandbox/Docker tidak tersedia (%s). Fallback ke subprocess.", err_str[:120]
                )
            else:
                # Error bukan dari Docker — lempar ke loop utama untuk self-correction
                raise

        # Fallback: subprocess langsung
        logging.info("Menjalankan kode via subprocess (fallback)...")
        stdout = self._run_code_subprocess(code_path, timeout=timeout_sec)
        logging.info("Subprocess berhasil. Output: %s", stdout[:200])
        return stdout

    def test_code(self, code_path):
        logging.info(f"Setting up sandbox environment for {code_path}. Running for {self.duration}s.")

        attempt = 1
        start_time = time.time()
        max_total_duration = 30 * 60

        while True:
            if time.time() - start_time > max_total_duration:
                logging.error("Total self-correction time exceeded 30 minutes. Aborting.")
                return False

            try:
                logging.info(f"Test Attempt {attempt}...")

                abs_code_path = os.path.abspath(code_path)

                if not os.path.exists(abs_code_path):
                    raise Exception(f"File tidak ditemukan: {abs_code_path}")

                # Step 1: Static Analysis
                is_valid, static_errors = self._static_analysis(abs_code_path)
                if not is_valid and "SyntaxError" in static_errors:
                    raise Exception(f"Static Analysis Failed:\n{static_errors}")

                # Step 2: Eksekusi (llm-sandbox Docker → subprocess fallback)
                stdout = self._execute_code(abs_code_path)

                logging.info(
                    "Sandbox testing passed successfully. Output: %s",
                    stdout[:200]
                )
                return True

            except Exception as e:
                error_msg = str(e)
                logging.warning(f"Execution failed: {error_msg}")
                logging.info("Initiating Self-Correction Loop...")

                search_context = self._search_error(error_msg[-200:])

                if self.llm:
                    prompt = (
                        f"The code at {code_path} failed with this error:\n{error_msg}\n\n"
                        f"Search context:\n{search_context}\n\n"
                        "Please provide the COMPLETE fixed Python code (no markdown fences, raw code only)."
                    )
                    logging.info("Asking LLM to fix code based on error and search context.")
                    try:
                        fixed_code = self.llm.generate_content(prompt, use_codegen_model=True)
                        if fixed_code:
                            if "```python" in fixed_code:
                                fixed_code = fixed_code.split("```python")[1].split("```")[0].strip()
                            elif "```" in fixed_code:
                                fixed_code = fixed_code.split("```")[1].strip()
                            with open(code_path, "w") as f:
                                f.write(fixed_code)
                            logging.info("Applied LLM fix to code.")
                    except Exception as llm_err:
                        logging.error(f"Failed to get fix from LLM: {llm_err}")

                if attempt >= 7:
                    logging.error("Failed 7 times. Initiating Graceful Cancellation to Client...")

                    if self.llm:
                        apology_prompt = (
                            f"I am an autonomous freelance AI agent. I failed to execute the script after 7 tries. "
                            f"The final error was: {error_msg[-300:]}. "
                            "Please generate a professional, polite message to the client apologizing for the delay "
                            "and explaining that I am stepping down from the project."
                        )
                        try:
                            advice = self.llm.generate_content(apology_prompt)
                        except Exception:
                            advice = None
                    else:
                        advice = None

                    if not advice:
                        advice = "I apologize, but I encountered an unresolvable technical error and must cancel this task."

                    logging.info(f"Apology generated: {advice}")

                    apology_file = "apology_message.txt"
                    with open(apology_file, "w") as f:
                        f.write(advice)
                    with open("cancellation_report.log", "a") as f:
                        f.write(f"Task Failed. Apology drafted to {apology_file}:\n{advice}\n\n")

                    return False

                attempt += 1
                time.sleep(5)
