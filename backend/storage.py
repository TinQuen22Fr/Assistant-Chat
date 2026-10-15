import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent


def files_dir() -> Path:
    path = Path(os.environ.get("FILES_DIR", "./data/files"))
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(user_id: str, file_id: str, ext: str, data: bytes) -> str:
    key = f"{user_id}/{file_id}{ext}"
    target = files_dir() / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return key


def path_of(key: str) -> Path:
    return files_dir() / key


def read(key: str) -> bytes:
    return path_of(key).read_bytes()


def delete(key: str) -> None:
    path_of(key).unlink(missing_ok=True)
