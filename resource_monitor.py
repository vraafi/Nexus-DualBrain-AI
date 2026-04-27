import psutil
import logging
import os
import shutil

class ResourceMonitor:
    def __init__(self, ram_threshold=85.0):
        self.ram_threshold = ram_threshold

    def is_safe_to_proceed(self):
        """Checks if current hardware resources (RAM, CPU, Disk I/O) are safe for heavy tasks."""
        ram_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.5)
        disk_usage = psutil.disk_usage('/').percent

        logging.info(f"Resource Monitor - RAM: {ram_percent}%, CPU: {cpu_percent}%, Disk: {disk_usage}%")

        if ram_percent > self.ram_threshold:
            logging.warning(f"RAM usage ({ram_percent}%) exceeds threshold ({self.ram_threshold}%). Unsafe to proceed.")
            return False

        # Add basic disk space check to prevent crashes on the 500GB HDD constraint
        if disk_usage > 95.0:
             logging.warning(f"Disk usage ({disk_usage}%) critically high. Attempting to clear temporary storage...")
             self._clear_storage_dirs()
             # Re-check after cleanup
             if psutil.disk_usage('/').percent > 95.0:
                 logging.error("Disk usage remains critical after cleanup. Unsafe to proceed.")
                 return False

        return True

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
