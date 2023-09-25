import json
import os
import pathlib
from base64 import b64encode
from functools import lru_cache
from typing import Optional

from rich import print


@lru_cache
def get_config_dir() -> pathlib.Path:
    cache_dir_root = os.path.expanduser("~")
    assert os.path.isdir(cache_dir_root)
    cache_dir = cache_dir_root + "/.crpy/"
    if not os.path.exists(cache_dir):
        print("Creating cache directory: " + cache_dir)
        os.makedirs(cache_dir)
    return pathlib.Path(cache_dir)


def get_config_file() -> pathlib.Path:
    cache_dir = get_config_dir()
    config_file = cache_dir / "config.json"
    if not config_file.is_file():
        config_file.write_text(json.dumps({"auths": {}}, indent=2))
    return config_file


def get_config() -> dict:
    config_file = get_config_file()
    try:
        config = json.loads(config_file.read_text())
        return config
    except json.JSONDecodeError:
        print(f"[red]Could not read config file at {config_file}: JSON is invalid[red]")
        return {}


def get_credentials(url: str) -> Optional[str]:
    creds = get_config()
    if "auths" in creds and url in creds["auths"] and "auth" in creds["auths"][url]:
        return creds["auths"][url]["auth"]
    return None


def save_credentials(url: str, username: str, password: str):
    creds = get_config()
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    creds["auths"][url] = {"auth": token}
    get_config_file().write_text(json.dumps(creds, indent=2))


def remove_credentials(url: str) -> bool:
    creds = get_config()
    removed = creds["auths"].pop(url, None)
    get_config_file().write_text(json.dumps(creds, indent=2))
    return removed is not None


def get_layer_path(layer: str) -> Optional[pathlib.Path]:
    cache_dir = get_config_dir() / "blobs/"
    os.makedirs(cache_dir, exist_ok=True)
    layer_path = cache_dir / layer.replace(":", "_")
    if layer_path.is_file():
        return layer_path
    return None


def save_layer(layer: str, layer_data: bytes):
    cache_dir = get_config_dir() / "blobs/"
    os.makedirs(cache_dir, exist_ok=True)
    layer_path = cache_dir / layer.replace(":", "_")
    with open(layer_path, mode="wb") as file:
        file.write(layer_data)


def get_layer_from_cache(layer: str) -> Optional[bytes]:
    layer_path = get_layer_path(layer)
    if layer_path:
        print(f"Using cache for layer {layer.split(':')[1][0:12]}")
        return layer_path.read_bytes()
    return None
