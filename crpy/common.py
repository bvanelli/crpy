import enum
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Optional, Union

import aiohttp


@dataclass
class Response:
    status: int
    data: bytes
    headers: Optional[dict] = None

    def json(self) -> dict:
        return json.loads(self.data)


async def _request(
    url,
    headers: dict = None,
    params: dict = None,
    data: Union[dict, bytes] = None,
    method: str = "post",
    aiohttp_kwargs: dict = None,
) -> Response:
    aiohttp_kwargs = aiohttp_kwargs or {}
    try:
        async with aiohttp.ClientSession() as session:
            method_fn = getattr(session, method)
            async with method_fn(url, headers=headers, params=params, data=data, **aiohttp_kwargs) as response:
                return Response(response.status, await response.read(), dict(response.headers))
    except aiohttp.ClientConnectionError as e:
        raise HTTPConnectionError(str(e))


async def _stream(url, headers: dict = None, aiohttp_kwargs: dict = None):
    aiohttp_kwargs = aiohttp_kwargs or {}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, **aiohttp_kwargs) as response:
            async for data, _ in response.content.iter_chunks():
                yield data


def compute_sha256(file: Union[str, io.BytesIO, bytes], use_prefix: bool = True):
    # If input is a string, consider it a filename
    if isinstance(file, str):
        with open(file, "rb") as f:
            content = f.read()
    # If input is BytesIO, get value directly
    elif isinstance(file, io.BytesIO):
        content = file.getvalue()
    elif isinstance(file, bytes):
        content = file
    else:
        raise TypeError("Invalid input type.")

    # Compute the sha256 hash
    sha256_hash = hashlib.sha256(content).hexdigest()
    return f"sha256:{sha256_hash}" if use_prefix else sha256_hash


class Platform(enum.Enum):
    # taken from https://github.com/docker-library/bashbrew/blob/v0.1.2/architecture/oci-platform.go#L14-L27
    LINUX = "linux/amd64"
    MAC = "linux/arm64/v8"
    WINDOWS = "windows/amd64"
    # less used platforms
    ARM_32_V5 = "linux/arm/v5"
    ARM_32_V6 = "linux/arm/v6"
    ARM_32_V7 = "linux/arm/v7"
    I386 = "linux/386"
    MIPS64lE = "linux/mips64le"
    PPC64LE = "linux/ppc64le"
    RISCV64 = "linux/riscv64"
    S390X = "linux/s390x"

    @classmethod
    def from_dict(cls, platform: dict) -> "Platform":
        return cls(platform_from_dict(platform))

    @property
    def os(self) -> str:
        return self.value.split("/")[0]

    @property
    def architecture(self) -> str:
        return self.value.split("/")[1]

    @property
    def variant(self) -> Optional[str]:
        split_value = self.value.split("/")
        return split_value[2] if len(split_value) > 2 else None


def platform_from_dict(platform: dict) -> str:
    base_str = f"{platform.get('os')}/{platform.get('architecture')}"
    if "variant" in platform:
        base_str += f"/{platform.get('variant')}"
    return base_str


# exceptions
class BaseCrpyError(Exception):
    pass


class UnauthorizedError(BaseCrpyError):
    pass


class HTTPConnectionError(BaseCrpyError):
    pass
