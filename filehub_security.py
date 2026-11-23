"""Application-level edit guard. NOT filesystem permissions or encryption."""
import hashlib
import hmac
import os
from pathlib import Path


def hash_password(password: str, salt: bytes | None = None, rounds: int = 240000) -> dict:
    if not password or len(password) < 8:
        raise ValueError("Mật khẩu cần ít nhất 8 ký tự.")
    salt = salt or os.urandom(16)
    return {"salt": salt.hex(), "hash": hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds).hex(), "rounds": rounds}


def verify_password(password: str, credential: dict) -> bool:
    try:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(credential["salt"]), int(credential["rounds"]))
        return hmac.compare_digest(digest, bytes.fromhex(credential["hash"]))
    except (KeyError, TypeError, ValueError):
        return False


def normalize(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def protected_path(path: str, protected: list[str]) -> bool:
    target = normalize(path)
    for item in protected:
        root = normalize(item)
        if target == root:
            return True
        if os.path.isdir(root):
            try:
                if os.path.commonpath([target, root]) == root:
                    return True
            except ValueError:
                pass
    return False


def update_paths(paths: list[str], old: str, new: str) -> list[str]:
    """Keep application lock entries aligned when renaming/moving protected items."""
    old_norm = normalize(old)
    output = []
    for p in paths:
        normalized = normalize(p)
        if normalized == old_norm:
            output.append(new)
        elif normalized.startswith(old_norm + os.sep):
            output.append(new + p[len(old):])
        else:
            output.append(p)
    return output
