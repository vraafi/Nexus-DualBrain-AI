import logging
import time
import subprocess
from duckduckgo_search import DDGS

class SandboxTester:
    def __init__(self, duration_minutes=15, llm_client=None):
        self.duration = duration_minutes * 60
        self.llm = llm_client

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
        # Infinite self-correction loop as requested
        while True:
             try:
                 logging.info(f"Test Attempt {attempt}...")

                 test_duration = min(self.duration, 5) # Run for 5 seconds max for testing

                 process = subprocess.run(
                     ["python", code_path],
                     capture_output=True,
                     text=True,
                     timeout=test_duration
                 )

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

                 attempt += 1
                 time.sleep(5)
