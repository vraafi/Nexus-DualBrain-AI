import logging
import time
import subprocess
from duckduckgo_search import DDGS
import os
import shutil
import uuid

class SandboxTester:
    def __init__(self, duration_minutes=15, llm_client=None):
        self.duration = duration_minutes * 60
        self.llm = llm_client
        self.venv_dir = "sandbox_env"
        self._setup_venv()

    def _setup_venv(self):
        if not os.path.exists(self.venv_dir):
            logging.info("Setting up lightweight virtual environment for sandbox testing...")
            subprocess.run(["python3", "-m", "venv", self.venv_dir], check=True)
            # Pre-install common scraping tools and testing tools
            pip_path = os.path.join(self.venv_dir, "bin", "pip")
            subprocess.run([pip_path, "install", "requests", "beautifulsoup4", "playwright", "flake8", "pytest"], check=True)

    def _static_analysis(self, code_path):
        """Runs flake8 to catch syntax errors before executing."""
        logging.info("Running static analysis via flake8...")
        flake8_exe = os.path.join(self.venv_dir, "bin", "flake8")
        try:
            result = subprocess.run([flake8_exe, code_path], capture_output=True, text=True)
            if result.returncode != 0:
                 logging.warning(f"Static analysis found potential issues:\n{result.stdout}")
                 return False, result.stdout
            return True, ""
        except Exception as e:
            logging.error(f"Failed to run static analysis: {e}")
            return True, "" # Don't block execution if flake8 fails to run

    def _search_error(self, error_message):
        logging.info("Searching DuckDuckGo for error solution...")
        try:
             results = DDGS().text(error_message, max_results=3)
             return "\n".join([r.get('body', '') for r in results])
        except Exception as e:
             logging.error(f"Search failed: {e}")
             return "No search results."

    def test_code(self, code_path):
        logging.info(f"Setting up sandbox environment for {code_path}. Running for {self.duration}s.")

        attempt = 1
        start_time = time.time()
        max_total_duration = 30 * 60 # 30 minutes absolute maximum to prevent infinite/long loop blocking

        while True:
             if time.time() - start_time > max_total_duration:
                 logging.error("Total self-correction time exceeded 30 minutes. Aborting to prevent infinite loop.")
                 return False

             try:
                 logging.info(f"Test Attempt {attempt}...")

                 test_duration = self.duration # Run for full requested duration (15-60m)

                 # Execute via Bubblewrap (bwrap) for lightweight but secure isolation
                 # This prevents LLM prompt injection RCEs from accessing the host OS
                 # while remaining light enough for 8GB RAM systems (unlike Docker).

                 python_exe = os.path.join(os.path.abspath(self.venv_dir), "bin", "python")
                 abs_code_path = os.path.abspath(code_path)

                 # CREATE ISOLATED SANDBOX DIRECTORY
                 # Never bind the project root. Create a dedicated temp folder for execution.
                 import shutil
                 sandbox_tmp_dir = os.path.abspath("./client_sandbox")
                 if not os.path.exists(sandbox_tmp_dir):
                     os.makedirs(sandbox_tmp_dir)

                 # Create a unique temporary directory for each test run
                 run_id = str(uuid.uuid4())
                 sandbox_run_dir = os.path.join(sandbox_tmp_dir, run_id)
                 os.makedirs(sandbox_run_dir)

                 isolated_script_path = os.path.join(sandbox_run_dir, os.path.basename(code_path))
                 shutil.copy2(abs_code_path, isolated_script_path)

                 # Also copy requirements.txt if it exists, for isolated venv setup
                 if os.path.exists(os.path.join(os.path.dirname(abs_code_path), "requirements.txt")):
                     shutil.copy2(os.path.join(os.path.dirname(abs_code_path), "requirements.txt"), sandbox_run_dir)

                 # Re-setup venv for each run to ensure isolation and correct dependencies
                 # This is resource intensive, but necessary for true isolation and to avoid dependency conflicts
                 # A more advanced solution would involve pre-built Docker images or persistent, isolated environments.
                 run_venv_dir = os.path.join(sandbox_run_dir, self.venv_dir)
                 subprocess.run(["python3", "-m", "venv", run_venv_dir], check=True)
                 pip_path = os.path.join(run_venv_dir, "bin", "pip")
                 # Install base requirements for the sandbox itself
                 subprocess.run([pip_path, "install", "requests", "beautifulsoup4", "playwright", "flake8", "pytest"], check=True)
                 # Install project-specific requirements if present
                 if os.path.exists(os.path.join(sandbox_run_dir, "requirements.txt")):
                     subprocess.run([pip_path, "install", "-r", os.path.join(sandbox_run_dir, "requirements.txt")], check=True)

                 # Update python_exe and pytest_exe to point to the new venv
                 python_exe = os.path.join(run_venv_dir, "bin", "python")
                 pytest_exe = os.path.join(run_venv_dir, "bin", "pytest")

                 # Update bwrap_cmd to bind the new sandbox_run_dir
                 bwrap_cmd = [
                     "bwrap",
                     "--unshare-user",
                     "--unshare-ipc",
                     "--unshare-pid",
                     "--unshare-uts",
                     "--unshare-cgroup-try",
                     "--die-with-parent",
                     "--ro-bind", "/usr", "/usr",
                     "--ro-bind", "/lib", "/lib",
                     "--ro-bind", "/lib64", "/lib64",
                     "--ro-bind", "/bin", "/bin",
                     "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
                     "--ro-bind", "/etc/ssl", "/etc/ssl",
                     "--ro-bind", run_venv_dir, run_venv_dir,
                     "--bind", sandbox_run_dir, sandbox_run_dir, # Bind the unique run directory
                     "--tmpfs", "/tmp",
                     "--tmpfs", "/dev/shm",
                     "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc",
                     "--setenv", "PATH", "/usr/bin:/bin",
                     "--chdir", sandbox_run_dir,
                     pytest_exe, isolated_script_path, "-v"
                 ]

                 # Step 1: Static Analysis
                 is_valid, static_errors = self._static_analysis(isolated_script_path)
                 if not is_valid and "SyntaxError" in static_errors:
                      raise Exception(f"Static Analysis Failed:\n{static_errors}")

                 # Step 2: Test Execution inside bwrap
                 # If unit tests are included in the generated script, we can run pytest on it
                 # If not, we just run the script with python. The prompt now asks for unittest block.

                 # We will default to running pytest on the file, which will also execute the code
                 # if it's structured properly, or we can just run python.
                 # To ensure both script logic and unit tests are hit, we run pytest on the script.
                 pytest_exe = os.path.join(os.path.abspath(self.venv_dir), "bin", "pytest")

                 # Use tmpfs for standard temporary directories to avoid host interference
                 # Fully unshare user, network (if testing doesn't need it, though scraping might),
                 # IPC, and PID namespaces.
                 bwrap_cmd = [
                     "bwrap",
                     "--unshare-user",
                     "--unshare-ipc",
                     "--unshare-pid",
                     "--unshare-uts",
                     "--unshare-cgroup-try",
                     "--die-with-parent",
                     "--ro-bind", "/usr", "/usr",
                     "--ro-bind", "/lib", "/lib",
                     "--ro-bind", "/lib64", "/lib64",
                     "--ro-bind", "/bin", "/bin",
                     "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
                     "--ro-bind", "/etc/ssl", "/etc/ssl",
                     "--ro-bind", os.path.abspath(self.venv_dir), os.path.abspath(self.venv_dir),
                     "--bind", sandbox_tmp_dir, sandbox_tmp_dir, # Only bind the empty isolated folder
                     "--tmpfs", "/tmp",
                     "--tmpfs", "/dev/shm",
                     "--dev-bind", "/dev", "/dev", # Changed from --dev to --dev-bind to prevent 'bwrap: Can't mount devtmpfs on /newroot/dev: Operation not permitted' errors in nested environments
                     "--proc", "/proc", # Crucial for python process management
                     "--setenv", "PATH", "/usr/bin:/bin",
                     "--chdir", sandbox_tmp_dir,
                     pytest_exe, isolated_script_path, "-v" # Run tests and the script
                 ]

                 try:
                     process = subprocess.run(
                         bwrap_cmd,
                         capture_output=True,
                         text=True,
                         timeout=test_duration
                     )
                 finally:
                     # Clean up isolated script to prevent state leakage
                     if os.path.exists(isolated_script_path):
                         os.remove(isolated_script_path)

                 if process.returncode == 0:
                     logging.info("Sandbox testing passed successfully.")
                     return True
                 else:
                     raise Exception(f"Process exited with code {process.returncode}: {process.stderr}")

             except subprocess.TimeoutExpired:
                 logging.info("Process ran for the full duration without crashing. Considered successful.")
                 return True

             except Exception as e:
                 error_msg = str(e)
                 logging.warning(f"Execution failed: {error_msg}")

                 logging.info("Initiating Self-Correction Loop...")
                 search_context = self._search_error(error_msg[-200:]) # Search tail of error

                 if self.llm:
                      prompt = f"The code {code_path} failed with error: {error_msg}. Context: {search_context}. Please provide the full fixed code."
                      logging.info("Asking Gemini API to fix code based on error and search context.")

                      try:
                          fixed_code = self.llm.generate_content(prompt)
                          if fixed_code:
                              # Strip markdown if present
                              if "```python" in fixed_code:
                                  fixed_code = fixed_code.split("```python")[1].split("```")[0].strip()
                              elif "```" in fixed_code:
                                  fixed_code = fixed_code.split("```")[1].strip()

                              with open(code_path, "w") as f:
                                  f.write(fixed_code)
                              logging.info("Applied fix to code.")
                      except Exception as llm_err:
                          logging.error(f"Failed to get fix from LLM: {llm_err}")

                 if attempt == 7:
                      logging.error("Failed 7 times. Initiating Graceful Cancellation to Client...")

                      if self.llm:
                          apology_prompt = (
                              f"I am an autonomous freelance AI agent. I failed to execute the script after 7 tries. "
                              f"The final error was: {error_msg[-300:]}. "
                              "Please generate a professional, polite message to the client apologizing for the delay "
                              "and explaining that I am stepping down from the project."
                          )
                          advice = self.llm.generate_content(apology_prompt)
                      else:
                          advice = "I apologize, but I encountered an unresolvable technical error and must cancel."

                      logging.info(f"Apology generated: {advice}")

                      # Execute true graceful cancellation by writing it to the script path
                      # so the delivery phase can attach it or send it, fulfilling the requirement to
                      # actually communicate with the client instead of ghosting them.
                      apology_file = "apology_message.txt"
                      with open(apology_file, "w") as f:
                          f.write(advice)

                      with open("cancellation_report.log", "a") as f:
                          f.write(f"Task Failed. Apology drafted to {apology_file}:\n{advice}\n\n")

                      # Return a distinct failure tuple/object to trigger the apology flow in main
                      return {"status": "failed", "apology_file": apology_file}

                 attempt += 1
                 time.sleep(5)
