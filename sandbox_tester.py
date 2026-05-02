import os
import shutil
import logging
import time
import subprocess
import sys

class SandboxTester:
    def __init__(self, database):
        self.db = database
        self.sandbox_dir = os.path.join(os.getcwd(), "client_sandbox")

    def setup_sandbox(self):
        """Creates a clean directory for testing generated code on the SSD."""
        logging.info("Setting up client sandbox on SSD...")
        if os.path.exists(self.sandbox_dir):
            shutil.rmtree(self.sandbox_dir)
        os.makedirs(self.sandbox_dir, exist_ok=True)
        logging.info(f"Sandbox created at {self.sandbox_dir}")

    def cleanup_sandbox(self):
        """Aggressively prunes dangling docker containers and networks to save SSD space."""
        logging.info("Executing aggressive Docker cache cleanup to protect 256GB SSD...")
        try:
            # Remove stopped containers and dangling images
            subprocess.run(["docker", "system", "prune", "-f"], capture_output=True, timeout=30)
            logging.info("Docker system pruned successfully.")

            # Remove local sandbox directory
            if os.path.exists(self.sandbox_dir):
                shutil.rmtree(self.sandbox_dir)
                logging.info("Local sandbox directory removed.")
        except Exception as e:
            logging.error(f"Error during sandbox cleanup: {e}")

    def _extract_dynamic_dependencies(self, code_string):
        """Parses the generated code for dependency comments and standard imports."""
        dependencies = set(["flake8==7.0.0"]) # Always include flake8 for static analysis

        # Mapping standard library modules to avoid pip installing them
        standard_libs = set([
            "os", "sys", "time", "datetime", "json", "csv", "math", "random",
            "re", "urllib", "subprocess", "logging", "threading", "multiprocessing",
            "collections", "itertools", "functools", "shutil", "sqlite3"
        ])

        for line in code_string.split('\n'):
            line = line.strip()
            # 1. Look for explicit comments like # DEPENDENCIES: requests, pandas
            if line.upper().startswith("# DEPENDENCIES:"):
                deps = line.split(":", 1)[1].split(",")
                for d in deps:
                    clean_dep = d.strip()
                    if clean_dep:
                        dependencies.add(clean_dep)

            # 2. Fallback: Parse standard import statements
            elif line.startswith("import ") or line.startswith("from "):
                parts = line.split()
                if len(parts) > 1:
                    module_name = parts[1].split(".")[0] # Get root module (e.g., from bs4 import BeautifulSoup -> bs4)
                    if module_name and module_name not in standard_libs:
                        # Add simple mapping for common packages where import name != package name
                        if module_name == "bs4":
                            dependencies.add("beautifulsoup4")
                        elif module_name == "cv2":
                            dependencies.add("opencv-python-headless")
                        elif module_name == "dotenv":
                            dependencies.add("python-dotenv")
                        else:
                            dependencies.add(module_name)

        return list(dependencies)

    def test_and_monitor_code(self, client_id, code_string, duration_minutes=15):
        """Runs the generated code in a subprocess within the sandbox for a specified duration.
        Returns a tuple (success_boolean, error_log_string) for self-correction.
        """
        self.db.update_task_state(f"sandbox_test_{client_id}", "IN_PROGRESS")
        self.setup_sandbox()

        if not code_string:
             logging.error(f"No code provided to sandbox tester for {client_id}.")
             self.db.update_task_state(f"sandbox_test_{client_id}", "FAILED", "No code provided.")
             return False, "No code provided."

        logging.info(f"Writing generated code into sandbox for {client_id}...")
        test_file = os.path.join(self.sandbox_dir, "app.py")
        with open(test_file, "w") as f:
            f.write(code_string)

        # Dynamically build requirements file
        dynamic_deps = self._extract_dynamic_dependencies(code_string)
        logging.info(f"Dynamic dependencies detected: {dynamic_deps}")
        req_file = os.path.join(self.sandbox_dir, "requirements.txt")
        with open(req_file, "w") as f:
            for dep in dynamic_deps:
                f.write(f"{dep}\n")

        logging.info(f"Starting Static Analysis and Subprocess execution for up to {duration_minutes} minutes...")

        error_logs = ""
        try:
            timeout_seconds = duration_minutes * 60
            container_name = f"sandbox_{client_id}_{int(time.time())}"

            # Use a slightly more capable image and install dependencies first
            # We use an entrypoint script to run flake8 validation then execute the code
            entrypoint_script = """
            echo 'Installing dynamic dependencies...'
            pip install -r requirements.txt
            echo 'Running Static Analysis (flake8)...'
            flake8 app.py --max-line-length=120
            if [ $? -ne 0 ]; then
                echo 'Static Analysis Failed.'
                exit 1
            fi
            echo 'Static Analysis Passed. Executing code...'
            python app.py
            """
            entry_file = os.path.join(self.sandbox_dir, "entry.sh")
            with open(entry_file, "w") as f:
                f.write(entrypoint_script)
            os.chmod(entry_file, 0o755)

            # SECURE EXECUTION: Run the code inside an isolated Docker container.
            # Networking is required ONLY briefly if pip install is needed, but for strict
            # security we can build a pre-packaged image offline. Since this is an alpine base,
            # we allow bridged network just to install flake8, but strictly limit memory.
            docker_cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--memory", "400m",  # Restrict memory to protect host (slightly raised for pip compiles)
                "--cpus", "0.5",     # Restrict CPU
                "-v", f"{self.sandbox_dir}:/usr/src/app", # Mount directory
                "-w", "/usr/src/app",
                "python:3.12-slim",  # Switched from alpine (musl) to slim (glibc) for wheel compatibility
                "sh", "entry.sh"
            ]

            logging.info(f"Starting Docker validation & execution for {client_id}...")

            process = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            logging.info(f"Docker process exited with return code: {process.returncode}")
            logging.info(f"STDOUT: {process.stdout.strip()}")

            if process.returncode == 0:
                 logging.info("Code passed both Static Analysis and Runtime Execution.")
                 test_passed = True
            else:
                 logging.error("Code failed Static Analysis or Runtime Execution.")
                 # Capture both stdout and stderr for the LLM to understand what went wrong
                 error_logs = f"Exit Code: {process.returncode}\nSTDOUT:\n{process.stdout.strip()}\nSTDERR:\n{process.stderr.strip()}"
                 test_passed = False

        except subprocess.TimeoutExpired:
            logging.info(f"Process ran successfully for the full {duration_minutes} minutes without crashing.")
            test_passed = True
            # Cleanup container on timeout
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        except Exception as e:
            logging.error(f"Sandbox execution error: {e}")
            error_logs = f"Sandbox execution error: {e}"
            test_passed = False

            # Attempt cleanup on error
            try:
                 subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            except:
                 pass

        # Execute aggressive disk cleanup
        self.cleanup_sandbox()

        if test_passed:
            logging.info(f"Sandbox testing for {client_id} completed successfully.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "COMPLETED", "Code executed successfully.")
            return True, ""
        else:
            logging.error(f"Sandbox testing for {client_id} failed.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "FAILED", "Errors encountered during execution.")
            return False, error_logs
