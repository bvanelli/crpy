import os
import pathlib
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class RegistryInfo:
    registry: str
    repository: str
    tag: str
    https: bool = True

    def manifest_url(self):
        return f"https://{self.registry}/v2/{self.repository}/manifests/{self.tag}"

    def blobs_url(self):
        return f"https://{self.registry}/v2/{self.repository}/blobs"

    @staticmethod
    def from_url(url: str) -> "RegistryInfo":
        """
        >>> args = RegistryInfo.from_url('index.docker.io/library/nginx')
        >>> args.registry
        'index.docker.io'
        >>> args.repository
        'library/nginx'
        >>> args.tag
        'latest'
        >>> name_parsed = RegistryInfo.from_url('gcr.io/distroless/cc:latest')
        >>> name_parsed.registry
        'gcr.io'
        >>> name_parsed.repository
        'distroless/cc'
        >>> name_parsed.tag
        'latest'
        """
        if "://" in url:
            scheme, url = url.split("://")
        else:
            scheme = "https"
        registry, repository_raw = url.split("/", 1)
        name, tag = (repository_raw.split(":") + ["latest"])[:2]
        return RegistryInfo(registry, name.strip("/"), tag, scheme == "https")

    @property
    def path(self):
        return f"/v2/{self.repository}/"


@lru_cache
def get_cache_dir() -> pathlib.Path:
    cache_dir_root = os.path.expanduser("~")
    assert os.path.isdir(cache_dir_root)
    cache_dir = cache_dir_root + "/.docker-pull-layers-cache/"
    if not os.path.exists(cache_dir):
        print("Creating cache directory: " + cache_dir)
        os.makedirs(cache_dir)
    return pathlib.Path(cache_dir)
