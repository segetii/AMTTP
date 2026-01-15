"""
Model Signing and Verification Utility

- Signs model files with a private key (ECDSA/secp256k1)
- Verifies model file signatures
- For production, use HSM-backed keys
"""
import hashlib
import os
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
import base64

KEY_PATH = os.environ.get("MODEL_SIGN_KEY", "model_signer.key")


def generate_key():
    sk = SigningKey.generate(curve=SECP256k1)
    with open(KEY_PATH, "wb") as f:
        f.write(sk.to_pem())
    print(f"Generated new signing key at {KEY_PATH}")
    return sk


def load_key():
    if not os.path.exists(KEY_PATH):
        return generate_key()
    with open(KEY_PATH, "rb") as f:
        return SigningKey.from_pem(f.read())


def sign_file(filepath):
    sk = load_key()
    with open(filepath, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).digest()
    sig = sk.sign(digest)
    sig_b64 = base64.b64encode(sig).decode()
    with open(filepath + ".sig", "w") as f:
        f.write(sig_b64)
    print(f"Signed {filepath}, signature saved to {filepath}.sig")
    return sig_b64


def verify_file(filepath, pubkey_path=None):
    with open(filepath, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).digest()
    with open(filepath + ".sig", "r") as f:
        sig = base64.b64decode(f.read())
    if pubkey_path:
        with open(pubkey_path, "rb") as f:
            vk = VerifyingKey.from_pem(f.read())
    else:
        sk = load_key()
        vk = sk.get_verifying_key()
    try:
        vk.verify(sig, digest)
        print(f"Signature valid for {filepath}")
        return True
    except BadSignatureError:
        print(f"Signature INVALID for {filepath}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python model_signing.py [sign|verify] <model_file>")
        exit(1)
    cmd, file = sys.argv[1], sys.argv[2]
    if cmd == "sign":
        sign_file(file)
    elif cmd == "verify":
        verify_file(file)
    else:
        print("Unknown command")
