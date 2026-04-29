import os
import json
import logging
from cryptography.fernet import Fernet

class IdentityManager:
    def __init__(self, vault_path="storage/identity_vault.enc", key_path="storage/vault.key"):
        self.vault_path = vault_path
        self.key_path = key_path
        self.fernet = None
        self._ensure_storage_dir()
        self._init_encryption()

    def _ensure_storage_dir(self):
        storage_dir = os.path.dirname(self.vault_path)
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir, exist_ok=True)

    def _init_encryption(self):
        """Initializes or loads the encryption key."""
        if not os.path.exists(self.key_path):
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as f:
                f.write(key)
            logging.info("Generated new encryption key for Identity Vault.")

        with open(self.key_path, "rb") as f:
            key = f.read()
            self.fernet = Fernet(key)

    def write_initial_mock_data(self):
        """Writes initial dummy data to the vault for testing purposes. Do NOT use with real data."""
        mock_data = {
            "full_name": "Autonomous Agent",
            "id_number": "1234567890123456",
            "address_data": "123 Agent Street, AI City, 10101",
            "identity_docs": "/path/to/dummy_id.jpg",
            "biometric_ref": "/path/to/dummy_face.jpg"
        }
        self.encrypt_and_save(mock_data)
        logging.info("Written initial mock data to Identity Vault.")

    def encrypt_and_save(self, data_dict):
        """Encrypts a dictionary and saves it to the vault."""
        json_data = json.dumps(data_dict).encode('utf-8')
        encrypted_data = self.fernet.encrypt(json_data)
        with open(self.vault_path, "wb") as f:
            f.write(encrypted_data)

    def decrypt_vault(self):
        """Decrypts the vault and returns the data dictionary."""
        if not os.path.exists(self.vault_path):
            logging.warning("Identity Vault does not exist.")
            return {}

        try:
            with open(self.vault_path, "rb") as f:
                encrypted_data = f.read()
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode('utf-8'))
        except Exception as e:
            logging.error(f"Failed to decrypt Identity Vault: {e}")
            return {}

    def get_field(self, field_name, context_domain):
        """
        Provides selective disclosure. Only returns the field if the domain is whitelisted.
        Logs the access with masking for security.
        """
        whitelisted_domains = ["upwork.com", "fiverr.com", "toptal.com", "google.com", "github.com"]

        is_safe = False
        for domain in whitelisted_domains:
             if domain in context_domain.lower():
                 is_safe = True
                 break

        if not is_safe:
             logging.error(f"SECURITY ALERT: Blocked attempt to access Identity Vault from unverified domain: {context_domain}")
             return None

        data = self.decrypt_vault()
        value = data.get(field_name)

        if value:
            # Mask logging for safety
            masked_value = str(value)[:2] + "*" * (len(str(value)) - 4) + str(value)[-2:] if len(str(value)) > 4 else "***"
            logging.info(f"Identity Vault: Accessed field '{field_name}' for domain '{context_domain}'. Masked value: {masked_value}")
            return value
        return None

    def auto_fill_kyc(self, browser_agent, platform_url):
        """
        Simulates parsing a KYC form and filling it with vault data.
        In a real scenario, this uses the LLM to map vault fields to DOM selectors.
        """
        logging.info(f"Attempting autonomous KYC auto-fill for {platform_url}...")

        # Security check
        full_name = self.get_field("full_name", platform_url)
        if not full_name:
             logging.warning("Cannot perform KYC: Vault empty or domain not whitelisted.")
             return False

        try:
             # Implementation of actual DOM filling would rely on LLM mapping
             # For the structure, we simulate a successful fill if data exists
             browser_agent.random_delay(2.0, 4.0)
             logging.info("Successfully filled KYC form via Identity Vault.")
             return True
        except Exception as e:
             logging.error(f"KYC Auto-fill failed: {e}")
             return False
