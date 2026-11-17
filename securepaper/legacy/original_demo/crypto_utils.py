"""AES-256-GCM, HMAC-SHA-256 and Shamir's Secret Sharing (k-of-n)."""
import os, hmac, hashlib, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PRIME = 2**521 - 1  # Mersenne prime, larger than any 256-bit key


def encrypt(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def sign(secret: bytes, data: bytes) -> str:
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


def split_secret(secret: bytes, k: int, n: int):
    s = int.from_bytes(secret, "big")
    coeffs = [s] + [secrets.randbelow(PRIME) for _ in range(k - 1)]
    shares = []
    for x in range(1, n + 1):
        y = 0
        for c in reversed(coeffs):
            y = (y * x + c) % PRIME
        shares.append(f"{x}-{y:x}")
    return shares


def recover_secret(shares, length: int = 32) -> bytes:
    pts = []
    for s in shares:
        a, b = s.strip().split("-")
        pts.append((int(a), int(b, 16)))
    total = 0
    for i, (xi, yi) in enumerate(pts):
        num = den = 1
        for j, (xj, _) in enumerate(pts):
            if i != j:
                num = num * (-xj) % PRIME
                den = den * (xi - xj) % PRIME
        total = (total + yi * num * pow(den, -1, PRIME)) % PRIME
    return total.to_bytes(length, "big")  # wrong shares -> OverflowError / bad key
