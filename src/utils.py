import hashlib
import json
import os
import pathlib
import enum
import tarfile
import tempfile

import aiohttp
from dataclasses import dataclass
from functools import lru_cache
from src.auth import get_token, get_url_from_auth_header
from typing import Optional, Union, List
import io
from async_lru import alru_cache


# taken from https://github.com/davedoesdev/dxf/blob/master/dxf/__init__.py#L24
_schema1_mimetype = "application/vnd.docker.distribution.manifest.v1+json"

_schema2_mimetype = "application/vnd.docker.distribution.manifest.v2+json"
_schema2_list_mimetype = "application/vnd.docker.distribution.manifest.list.v2+json"

# OCIv1 equivalent of a docker registry v2 manifests
_ociv1_manifest_mimetype = "application/vnd.oci.image.manifest.v1+json"
# OCIv1 equivalent of a docker registry v2 "manifests list"
_ociv1_index_mimetype = "application/vnd.oci.image.index.v1+json"


@dataclass
class Response:
    status: int
    data: bytes
    headers: Optional[dict] = None

    def json(self) -> dict:
        return json.loads(self.data)


async def _get(url, headers: dict = None) -> Response:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return Response(response.status, await response.read(), dict(response.headers))


async def _stream(url, headers: dict = None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            async for data, _ in response.content.iter_chunks():
                yield data


def compute_sha256(file: Union[str, io.BytesIO, bytes]):
    # If input is a string, consider it a filename
    if isinstance(file, str):
        with open(file, 'rb') as f:
            content = f.read()
    # If input is BytesIO, get value directly
    elif isinstance(file, io.BytesIO):
        content = file.getvalue()
    elif isinstance(file, bytes):
        content = file
    else:
        raise TypeError('Invalid input type.')

    # Compute the sha256 hash
    sha256_hash = hashlib.sha256(content).hexdigest()

    return sha256_hash


class Platform(enum.Enum):
    LINUX = "linux/amd64"
    MAC = "linux/arm64/v8"


def platform_from_dict(platform: dict):
    base_str = f"{platform.get('os')}/{platform.get('architecture')}"
    if "variant" in platform:
        base_str += f"/{platform.get('variant')}"
    return base_str


@dataclass
class RegistryInfo:
    """
    See https://containers.gitbook.io/build-containers-the-hard-way/ for an in depth explanation of what is going on.
    """

    registry: str
    repository: str
    tag: str
    https: bool = True
    token: Optional[str] = None

    @property
    def _headers(self) -> dict:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def manifest_url(self):
        method = "https" if self.https else "http"
        return f"{method}://{self.registry}/v2/{self.repository}/manifests/{self.tag}"

    def blobs_url(self):
        method = "https" if self.https else "http"
        return f"{method}://{self.registry}/v2/{self.repository}/blobs"

    def __hash__(self):
        return hash((self.registry, self.registry, self.tag, self.https))

    def __str__(self):
        return f"{self.registry}/{self.repository}:{self.tag}"

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
        if url.count("/") == 0 or (url.count("/") == 1 and "." not in url):
            registry, repository_raw = "index.docker.io", f"library/{url}"
        else:
            registry, repository_raw = url.split("/", 1)
        name, tag = (repository_raw.split(":") + ["latest"])[:2]
        return RegistryInfo(registry, name.strip("/"), tag, scheme == "https")

    @property
    def path(self):
        return f"/v2/{self.repository}/"

    @alru_cache
    async def get_manifest(self, fat: bool = False) -> Response:
        """
        Gets the manifest for a remote docker image. This is a JSON file containing the metadata for how the image is
        stored.
        :param fat: If it should return the manifest list, rather than the default manifest. This allows the user to
            also select multiple architectures instead of being limited in just the default one.
            See https://docs.docker.com/registry/spec/manifest-v2-2/ for explanation.
        :return: Response object with status code, raw data and response headers.
        """
        if fat:
            headers = {
                "Accept": ", ".join(
                    (
                        _schema1_mimetype,
                        _schema2_mimetype,
                        _schema2_list_mimetype,
                        _ociv1_manifest_mimetype,
                        _ociv1_index_mimetype,
                    )
                )
            }
        else:
            headers = {
                "Accept": ", ".join(
                    (
                        _schema1_mimetype,
                        _schema2_mimetype,
                    )
                )
            }
        response = await _get(self.manifest_url(), headers | self._headers)
        if response.status == 401:
            www_auth = response.headers["WWW-Authenticate"]
            assert www_auth.startswith('Bearer realm="')
            # reuse this token in consecutive requests
            self.token = get_token(get_url_from_auth_header(www_auth))
            print(f"Authenticated at {self}")
            response = await _get(self.manifest_url(), headers | self._headers)
        return response

    @alru_cache
    async def get_manifest_from_architecture(self, architecture: Union[str, Platform] = None) -> dict:
        if isinstance(architecture, Platform):
            architecture = architecture.value
        if architecture is not None:
            manifests = (await self.get_manifest(fat=True)).json()
            available_architectures = [platform_from_dict(manifest["platform"]) for manifest in manifests["manifests"]]
            for idx, a in enumerate(available_architectures):
                if a == architecture:
                    return manifests["manifests"][idx]
            raise ValueError(f"Architecture {architecture} not found for image {self}")
        else:
            return (await self.get_manifest()).json()

    @alru_cache
    async def get_config(self, architecture: Union[str, Platform] = None) -> Response:
        """
        Gets the config of a docker image. The config contains all basic information of a docker image, including the
        entrypoints, cmd, environment variables, etc.

        :param architecture: optional architecture for the image. If not provided, the default registry architecture
            will be pulled.
        :return: Response object with status code, raw data and response headers.
        """
        manifest = await self.get_manifest_from_architecture(architecture)
        config_digest = manifest["config"]["digest"]
        response = await _get(f"{self.blobs_url()}/{config_digest}", self._headers)
        return response

    @alru_cache
    async def get_layers(self, architecture: Union[str, Platform] = None) -> List[str]:
        """
        Gets the digests for each layer available at the remote registry.
        :param architecture: optional architecture for the image. If not provided, the default registry architecture
            will be pulled.
        :return:
        """
        manifest = await self.get_manifest_from_architecture(architecture)
        layers = [m["digest"] for m in manifest["layers"]]
        return layers

    async def pull_layer(self, layer: str, file_obj=None) -> Optional[bytes]:
        if file_obj is None:
            response = await _get(f"{self.blobs_url()}/{layer}", self._headers)
            return response.data
        else:
            async for chunk in _stream(f"{self.blobs_url()}/{layer}", self._headers):
                file_obj.write(chunk)

    async def pull(self, output_file: Union[str, pathlib.Path, io.BytesIO], architecture: Union[str, Platform] = None):
        with tempfile.TemporaryDirectory() as temp_dir:
            web_manifest = await self.get_manifest_from_architecture(architecture)
            config = await self.get_config(architecture)

            config_filename = f'{web_manifest["config"]["digest"].split(":")[1]}.json'
            with open(f"{temp_dir}/{config_filename}", "wb") as outfile:
                outfile.write(config.data)

            layer_path_l = []
            for layer in await self.get_layers():
                layer_folder = layer.split(":")[-1]
                path = layer_folder + "/layer.tar"
                print(f"Pulling layer {layer_folder}")
                layer_bytes = await self.pull_layer(layer)
                os.makedirs(f"{temp_dir}/{layer_folder}", exist_ok=True)
                with open(f"{temp_dir}/{path}", "wb") as f:
                    f.write(layer_bytes)
                layer_path_l.append(path)

            manifest = [{"Config": config_filename, "RepoTags": [str(self)], "Layers": layer_path_l}]
            with open(f"{temp_dir}/manifest.json", "w") as outfile:
                json.dump(manifest, outfile)

            if isinstance(output_file, io.BytesIO):
                output_kwargs = dict(fileobj=output_file, mode="w")
            else:
                output_kwargs = dict(name=output_file, mode="w")
            with tarfile.open(**output_kwargs) as tar_out:
                os.chdir(temp_dir)
                tar_out.add(".")


@lru_cache
def get_cache_dir() -> pathlib.Path:
    cache_dir_root = os.path.expanduser("~")
    assert os.path.isdir(cache_dir_root)
    cache_dir = cache_dir_root + "/.docker-pull-push/"
    if not os.path.exists(cache_dir):
        print("Creating cache directory: " + cache_dir)
        os.makedirs(cache_dir)
    return pathlib.Path(cache_dir)
