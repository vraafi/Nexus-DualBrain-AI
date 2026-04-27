import psutil
import logging

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
             logging.warning(f"Disk usage ({disk_usage}%) critically high. Unsafe to download videos or write large files.")
             return False

        return True
