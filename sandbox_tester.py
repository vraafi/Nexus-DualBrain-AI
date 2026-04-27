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
        """Creates a clean directory for testing generated code."""
        logging.info("Setting up client sandbox...")
        if os.path.exists(self.sandbox_dir):
            shutil.rmtree(self.sandbox_dir)
        os.makedirs(self.sandbox_dir, exist_ok=True)
        logging.info(f"Sandbox created at {self.sandbox_dir}")

    def test_and_monitor_code(self, client_id, code_string, duration_minutes=15):
        """Runs the generated code in a subprocess within the sandbox for a specified duration."""
        self.db.update_task_state(f"sandbox_test_{client_id}", "IN_PROGRESS")
        self.setup_sandbox()

        if not code_string:
             logging.error(f"No code provided to sandbox tester for {client_id}.")
             self.db.update_task_state(f"sandbox_test_{client_id}", "FAILED", "No code provided.")
             return False

        logging.info(f"Writing generated code into sandbox for {client_id}...")
        test_file = os.path.join(self.sandbox_dir, "app.py")
        with open(test_file, "w") as f:
            f.write(code_string)

        logging.info(f"Starting actual subprocess execution and monitoring for up to {duration_minutes} minutes...")

        try:
            timeout_seconds = duration_minutes * 60

            # SECURE EXECUTION: Run the code inside an isolated Docker container.
            # This prevents host filesystem access and network exfiltration of secrets.
            container_name = f"sandbox_{client_id}_{int(time.time())}"
            docker_cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", "none", # Block network access to prevent exfiltration
                "--memory", "256m",  # Restrict memory to protect host
                "--cpus", "0.5",     # Restrict CPU
                "-v", f"{self.sandbox_dir}:/usr/src/app:ro", # Read-only mount of the generated code
                "-w", "/usr/src/app",
                "python:3.12-alpine",
                "python", "app.py"
            ]

            logging.info(f"Starting Docker execution for {client_id}...")

            process = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            logging.info(f"Docker process exited with return code: {process.returncode}")
            logging.info(f"STDOUT: {process.stdout.strip()}")
            if process.stderr:
                logging.warning(f"STDERR: {process.stderr.strip()}")

            if process.returncode == 0:
                 test_passed = True
            else:
                 test_passed = False

        except subprocess.TimeoutExpired:
            logging.info(f"Process ran successfully for the full {duration_minutes} minutes without crashing.")
            test_passed = True
            # Cleanup container on timeout
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        except Exception as e:
            logging.error(f"Sandbox execution error: {e}")
            test_passed = False

            # Attempt cleanup on error
            try:
                 subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            except:
                 pass

        if test_passed:
            logging.info(f"Sandbox testing for {client_id} completed successfully.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "COMPLETED", "Code executed successfully.")
            return True
        else:
            logging.error(f"Sandbox testing for {client_id} failed.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "FAILED", "Errors encountered during execution.")
            return False
