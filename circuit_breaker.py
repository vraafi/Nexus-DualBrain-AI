import time
import logging

class CircuitBreaker:
    """Mencegah crash berulang saat platform mengganti UI atau sedang down"""
    
    def __init__(self, platform_name, failure_threshold=5, recovery_timeout=3600):
        self.platform_name = platform_name
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logging.info(f"[CircuitBreaker] {self.platform_name} mencoba HALF_OPEN...")
                self.state = "HALF_OPEN"
            else:
                raise Exception(f"Circuit breaker for {self.platform_name} is OPEN - platform mungkin down atau UI berubah")
                
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                logging.info(f"[CircuitBreaker] {self.platform_name} kembali CLOSED (Sukses)")
                self._reset()
            return result
        except Exception as e:
            self._record_failure()
            raise e
            
    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logging.error(f"[CircuitBreaker] {self.platform_name} OPENED - {self.failure_threshold} kegagalan berturut-turut")
            
    def _reset(self):
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_failure_time = None
