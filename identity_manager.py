import json
import os
import logging
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VAULT_FILE = "identity_vault.enc"
SALT_FILE = "vault.salt"

class IdentityManager:
    def __init__(self):
        self.key = self._derive_key()
        self.cipher = Fernet(self.key)

    def _derive_key(self):
        password = os.environ.get("VAULT_PASSWORD", "default_insecure_password_change_me").encode()

        if not os.path.exists(SALT_FILE):
            salt = os.urandom(16)
            with open(SALT_FILE, "wb") as f:
                f.write(salt)
            logging.info("Generated new salt for Identity Vault.")
        else:
            with open(SALT_FILE, "rb") as f:
                salt = f.read()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

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
