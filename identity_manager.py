import json
import os
import logging
from cryptography.fernet import Fernet

VAULT_FILE = "identity_vault.enc"
KEY_FILE = "vault.key"

class IdentityManager:
    def __init__(self):
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    def _load_or_create_key(self):
        if not os.path.exists(KEY_FILE):
            key = Fernet.generate_key()
            with open(KEY_FILE, "wb") as f:
                f.write(key)
            logging.info("Generated new encryption key for Identity Vault.")
            return key
        with open(KEY_FILE, "rb") as f:
            return f.read()

    def _read_vault(self):
        if not os.path.exists(VAULT_FILE):
            return {}
        try:
            with open(VAULT_FILE, "rb") as f:
                encrypted_data = f.read()
            decrypted_data = self.cipher.decrypt(encrypted_data).decode()
            return json.loads(decrypted_data)
        except Exception as e:
            logging.error(f"Failed to read vault: {e}")
            return {}

    def _write_vault(self, data):
        try:
            encrypted_data = self.cipher.encrypt(json.dumps(data).encode())
            with open(VAULT_FILE, "wb") as f:
                f.write(encrypted_data)
        except Exception as e:
            logging.error(f"Failed to write to vault: {e}")

    def save_credential(self, platform, username, password):
        vault = self._read_vault()
        vault[platform] = {"username": username, "password": password}
        self._write_vault(vault)
        logging.info(f"Saved credentials securely for platform: {platform}")

    def get_credential(self, platform):
        vault = self._read_vault()
        cred = vault.get(platform)
        if cred:
            # Mask logging per requirements
            masked_user = cred['username'][:3] + "..." + cred['username'][-2:]
            logging.info(f"Retrieved credentials for {platform} (User: {masked_user})")
            return cred
        logging.warning(f"No credentials found for {platform}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = IdentityManager()
    mgr.save_credential("upwork", "freelance_ai@example.com", "super_secret_password")
    cred = mgr.get_credential("upwork")
    print(f"Test retrieval successful: {bool(cred)}")
