import io
import json
import os
import pathlib
import tarfile
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Union

from crpy.common import compute_sha256

INPUT_TYPES = Union[bytes, pathlib.Path, str, io.StringIO, dict, None]


@dataclass
class Blob:
    path: Optional[pathlib.Path] = None
    content: Optional[bytes] = None
    filename: Optional[pathlib.Path] = None
    digest: Optional[str] = None

    @classmethod
    def from_any(cls, value: INPUT_TYPES, digest: str = None) -> "Blob":
        if isinstance(value, str):
            return cls(pathlib.Path(value), digest=digest)
        elif isinstance(value, pathlib.Path):
            return cls(value, digest=digest)
        elif isinstance(value, bytes):
            return cls(None, value, digest=digest)
        elif isinstance(value, io.StringIO):
            return cls(None, value.read().encode(), digest=digest)
        elif isinstance(value, dict):
            return cls(None, json.dumps(value).encode(), digest=digest)

    def as_bytes(self):
        if self.path:
            return self.path.read_bytes()
        else:
            return self.content

    def as_dict(self):
        return json.loads(self.as_bytes())

    def sha256_sum(self):
        file = self.path if self.path is not None else self.content
        if not self.digest:
            self.digest = compute_sha256(file, use_prefix=False)
        return self.digest


class Image:
    """
    Component to interact with docker images for the purpose of building and generating tar-files with the correct
    layers. This can be populated at will and written to disk, having the individual blobs modified.
    """

    def __init__(self, config: dict = None, manifest: dict = None, layers: List[bytes] = None):
        self._config: Optional[Blob] = None
        self._manifest: Optional[Blob] = None
        self._layers: Optional[List[Blob]] = None
        self.config = config
        self.manifest = manifest
        self.layers = layers or []

    @property
    def manifest(self) -> Blob:
        return self._manifest

    @manifest.setter
    def manifest(self, value: INPUT_TYPES):
        self._manifest = Blob.from_any(value)

    @property
    def config(self) -> Blob:
        return self._config

    @config.setter
    def config(self, value: INPUT_TYPES):
        self._config = Blob.from_any(value)

    @property
    def layers(self) -> List[Blob]:
        return self._layers

    @layers.setter
    def layers(self, layers: List[INPUT_TYPES]):
        self._layers = [Blob.from_any(layer) for layer in layers]

    def to_disk(self, filename: pathlib.Path, tags: List[str] = None):
        with tempfile.TemporaryDirectory() as temp_dir:
            web_manifest = self.manifest.as_dict()
            config_filename = f'{web_manifest["config"]["digest"].split(":")[1]}.json'
            with open(f"{temp_dir}/{config_filename}", "wb") as outfile:
                outfile.write(self.config.as_bytes())

            layer_path_l = []
            for layer in self.layers:
                layer_bytes = layer.as_bytes()
                layer_folder = layer.sha256_sum()
                path = layer_folder + "/layer.tar"
                os.makedirs(f"{temp_dir}/{layer_folder}", exist_ok=True)
                with open(f"{temp_dir}/{path}", "wb") as f:
                    f.write(layer_bytes)
                layer_path_l.append(path)

            manifest = [{"Config": config_filename, "RepoTags": tags or [], "Layers": layer_path_l}]
            with open(f"{temp_dir}/manifest.json", "w") as outfile:
                json.dump(manifest, outfile)

            if isinstance(filename, io.BytesIO):
                output_kwargs = {"fileobj": filename, "mode": "w"}
            else:
                output_kwargs = {"name": filename, "mode": "w"}
            with tarfile.open(**output_kwargs) as tar_out:
                os.chdir(temp_dir)
                tar_out.add(".")
                os.chdir("..")
