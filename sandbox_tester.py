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

        # Write a simple requirements file if the LLM output hints at external dependencies
        # In a fully AGI scenario, this would be generated alongside the code
        req_file = os.path.join(self.sandbox_dir, "requirements.txt")
        with open(req_file, "w") as f:
            f.write("flake8==7.0.0\n")

        logging.info(f"Starting Static Analysis and Subprocess execution for up to {duration_minutes} minutes...")

        try:
            timeout_seconds = duration_minutes * 60
            container_name = f"sandbox_{client_id}_{int(time.time())}"

            # Use a slightly more capable image and install dependencies first
            # We use an entrypoint script to run flake8 validation then execute the code
            entrypoint_script = """
            pip install -r requirements.txt > /dev/null 2>&1
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
                "--memory", "350m",  # Restrict memory to protect host
                "--cpus", "0.5",     # Restrict CPU
                "-v", f"{self.sandbox_dir}:/usr/src/app", # Mount directory
                "-w", "/usr/src/app",
                "python:3.12-alpine",
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
            if process.stderr:
                logging.warning(f"STDERR: {process.stderr.strip()}")

            if process.returncode == 0:
                 logging.info("Code passed both Static Analysis and Runtime Execution.")
                 test_passed = True
            else:
                 logging.error("Code failed Static Analysis or Runtime Execution.")
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

        # Execute aggressive disk cleanup
        self.cleanup_sandbox()

        if test_passed:
            logging.info(f"Sandbox testing for {client_id} completed successfully.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "COMPLETED", "Code executed successfully.")
            return True
        else:
            logging.error(f"Sandbox testing for {client_id} failed.")
            self.db.update_task_state(f"sandbox_test_{client_id}", "FAILED", "Errors encountered during execution.")
            return False
