import psutil
import logging
import os
import shutil

class ResourceMonitor:
    def __init__(self, ram_threshold=80.0):
        self.ram_threshold = ram_threshold

    def is_safe_to_proceed(self):
        """Checks if current hardware resources (RAM, CPU, Disk I/O) are safe for heavy tasks."""
        ram_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.5)
        disk_usage = psutil.disk_usage('/').percent

        logging.info(f"Resource Monitor - RAM: {ram_percent}%, CPU: {cpu_percent}%, Disk: {disk_usage}%")

        if ram_percent > self.ram_threshold:
            logging.warning(f"RAM usage ({ram_percent}%) exceeds strict threshold ({self.ram_threshold}%). Attempting aggressive cleanup...")
            self._aggressively_kill_browsers()

            # Re-check RAM after kill attempt
            if psutil.virtual_memory().percent > self.ram_threshold:
                 logging.error("RAM usage remains critically high after aggressive cleanup. Halting tasks.")
                 return False
            else:
                 logging.info("RAM recovered after aggressive process termination. Proceeding carefully.")

        # Add basic disk space check to prevent crashes on the 500GB HDD constraint
        if disk_usage > 95.0:
             logging.warning(f"Disk usage ({disk_usage}%) critically high. Attempting to clear temporary storage...")
             self._clear_storage_dirs()
             # Re-check after cleanup
             if psutil.disk_usage('/').percent > 95.0:
                 logging.error("Disk usage remains critical after cleanup. Unsafe to proceed.")
                 return False

        return True

    def _aggressively_kill_browsers(self):
        """Actively kills orphaned Chromium processes that might be hoarding the 8GB RAM."""
        killed_count = 0
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = proc.info['name']
                    cmdline = proc.info['cmdline']
                    # Look for Playwright/Chromium processes
                    if name and ('chrome' in name.lower() or 'chromium' in name.lower()):
                        # Only kill playwright processes to avoid killing user's own browser if they are using it
                        if cmdline and any('playwright' in arg.lower() for arg in cmdline):
                            proc.kill()
                            killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            logging.info(f"Aggressively terminated {killed_count} orphaned browser processes to free RAM.")
        except Exception as e:
            logging.error(f"Error during aggressive RAM cleanup: {e}")

    def _clear_storage_dirs(self):
        """Actively clears downloaded and generated files to free up disk space."""
        dirs_to_clear = ["downloads", "veo_outputs"]
        for d in dirs_to_clear:
            dir_path = os.path.join(os.getcwd(), d)
            if os.path.exists(dir_path):
                try:
                    for filename in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, filename)
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    logging.info(f"Cleared directory: {d}")
                except Exception as e:
                    logging.error(f"Failed to clear {d}: {e}")
