"""
bcrypt password hashing.

Cost factor 12: ~250 ms per hash on a laptop, which is a negligible share of
a login while still being far beyond what a stolen hash is worth cracking.
"""

from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except (ValueError, TypeError):
        # Malformed or empty stored hash: treat as "not a match" rather than
        # letting a corrupted row 500 the login endpoint.
        return False
