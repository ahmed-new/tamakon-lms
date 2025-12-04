# pip install cryptography
import base64, hashlib
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

def _fernet():
    key = getattr(settings, "PAYPAL_SECRET_ENC_KEY", None)
    if not key:
        # fallback آمن مشتق من SECRET_KEY (ويُفضّل تضيف PAYPAL_SECRET_ENC_KEY في env)
        dk = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(dk)
    elif isinstance(key, str):
        key = key.encode()
    return Fernet(key)

def encrypt(text: str) -> str:
    if not text:
        return ""
    return _fernet().encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
