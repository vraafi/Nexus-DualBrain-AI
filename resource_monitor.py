import psutil
import logging

class ResourceMonitor:
    def __init__(self, ram_threshold=85.0):
        self.ram_threshold = ram_threshold

    def is_safe_to_proceed(self):
        """Checks if current hardware resources are safe for heavy tasks."""
        ram_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.5)

        logging.info(f"Resource Monitor - RAM: {ram_percent}%, CPU: {cpu_percent}%")

        if ram_percent > self.ram_threshold:
            logging.warning(f"RAM usage ({ram_percent}%) exceeds threshold ({self.ram_threshold}%). Unsafe to proceed.")
            return False

        return True
