import os
import json
from base64 import b64encode, b64decode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecureStorage:
    def __init__(self, storage_path: str = None):
        """Initialize secure storage with encryption.
        
        Args:
            storage_path (str, optional): Path to storage directory. If not provided,
                                        uses 'secure_storage' in current directory.
        """
        if storage_path is None:
            # Use directory relative to the script location
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.storage_path = os.path.join(script_dir, "secure_storage")
        else:
            self.storage_path = os.path.abspath(storage_path)
            
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
        
        # Get encryption key from environment or generate new one
        self.key = os.environ.get('BACKSTAGE_ENCRYPTION_KEY', '').encode()
        if not self.key:
            print("Warning: BACKSTAGE_ENCRYPTION_KEY not found in environment. Generating new key...")
            self.key = Fernet.generate_key()
            print("Please set the following key in your environment:")
            print(f"BACKSTAGE_ENCRYPTION_KEY={self.key.decode()}")
        
        self.cipher = Fernet(self.key)
    
    def encrypt(self, data: str) -> bytes:
        """Encrypt string data."""
        return self.cipher.encrypt(data.encode())
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt bytes to string."""
        return self.cipher.decrypt(encrypted_data).decode()
    
    def save_org_config(self, org_name: str, config: dict):
        """Save encrypted organization configuration."""
        encrypted_data = self.encrypt(json.dumps(config))
        file_path = os.path.join(self.storage_path, f"{org_name}.enc")
        with open(file_path, "wb") as f:
            f.write(encrypted_data)
    
    def load_org_config(self, org_name: str) -> dict:
        """Load and decrypt organization configuration."""
        file_path = os.path.join(self.storage_path, f"{org_name}.enc")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            encrypted_data = f.read()
        return json.loads(self.decrypt(encrypted_data))
    
    def list_organizations(self) -> list:
        """List all saved organizations."""
        orgs = []
        for file in os.listdir(self.storage_path):
            if file.endswith(".enc"):
                orgs.append(file[:-4])  # Remove .enc extension
        return orgs
