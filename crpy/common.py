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
    url, headers: dict = None, params: dict = None, data: Union[dict, bytes] = None, method: str = "post"
) -> Response:
    async with aiohttp.ClientSession(trust_env=True) as session:
        method_fn = getattr(session, method)
        async with method_fn(url, headers=headers, params=params, data=data) as response:
            return Response(response.status, await response.read(), dict(response.headers))


async def _stream(url, headers: dict = None):
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(url, headers=headers) as response:
            async for data, _ in response.content.iter_chunks():
                yield data


def compute_sha256(file: Union[str, io.BytesIO, bytes]):
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

    return f"sha256:{sha256_hash}"


class Platform(enum.Enum):
    LINUX = "linux/amd64"
    MAC = "linux/arm64/v8"


def platform_from_dict(platform: dict):
    base_str = f"{platform.get('os')}/{platform.get('architecture')}"
    if "variant" in platform:
        base_str += f"/{platform.get('variant')}"
    return base_str


# exceptions
class UnauthorizedError(Exception):
    pass
