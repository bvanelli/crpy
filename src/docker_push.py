#!/usr/bin/env python

# Still to do:
# * Check compatibility with Python2 and Python3 during tests
# * Check if the layer already exists with a HEAD request
# * Handle Authentification

from tempfile import mkdtemp
import tarfile
import sys
import os
import hashlib
import json
from os.path import join
import shutil
import requests
from src.utils import RegistryInfo


def compute_digest(filename):
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return "sha256:" + sha256_hash.hexdigest()


def perform_request(
    method, registry: RegistryInfo, path: str, body: dict = None, headers: dict = None
) -> requests.Response:
    """
    See also: https://mail.python.org/pipermail/web-sig/2007-April/002662.html
    """
    response = None
    try:
        full_path = registry.path + path
        print(f">  {method} {registry.registry} {full_path}")
        response = getattr(requests, method.lower())(full_path, body=body, headers=headers)
    finally:
        if response is not None:
            data = response.content
            if len(data) > 0 and response.status_code not in [201, 202]:
                print(data)
    print("    Return:" + str(response.status_code))  # response.getcode())
    return response


def upload_blob(registry, src_f, media_type):
    print("* Uploading " + src_f)
    r = perform_request("POST", registry, "blobs/uploads/")

    location = r.headers["Location"]

    # TODO: extract and unit test
    location_no_root = location[location.find(registry.path) + len(registry.path) :]
    with open(src_f, "rb") as content_file:
        content = content_file.read()
    location_with_digest = (
        location_no_root[: location_no_root.find("?") + 1]
        + "digest="
        + compute_digest(src_f)
        + "&"
        + location_no_root[location_no_root.find("?") + 1 :]
    )
    perform_request(
        "PUT",
        registry,
        location_with_digest,
        content,
        {"Content-Type": "application/octet-stream", "Content-Length": str(len(content))},  # 'application/octet-stream'
    )


def upload_manifest(registry, manifest):
    print("* Uploading manifest")
    headers = {"Content-Type": "application/vnd.docker.distribution.manifest.v2+json"}
    perform_request("PUT", registry, "manifests/latest", manifest, headers)


def get_file_size(f):
    return os.path.getsize(f)


def build_manifest(config_f, layers_f):
    json_d = {}
    json_d["schemaVersion"] = 2
    json_d["mediaType"] = "application/vnd.docker.distribution.manifest.v2+json"
    json_d["config"] = {
        "digest": compute_digest(config_f),
        "size": get_file_size(config_f),
        "mediaType": "application/vnd.docker.container.image.v1+json",
    }
    json_d["layers"] = []
    for layer_f in layers_f:
        # TODO: check the layer is indeed compressed
        json_d["layers"].append(
            {
                "digest": compute_digest(layer_f),
                "size": get_file_size(layer_f),
                "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
            }
        )
    return json.dumps(json_d)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("docker-push source destination")
        print("  Example: docker-push my-image http://registry:5000/my-repository")
        exit(1)

    src = sys.argv[1]
    assert os.path.isfile(src), src + " is not a file / does not exist"
    repository_url = RegistryInfo.from_url(sys.argv[2])
    try:
        temp_dir = mkdtemp()
        try:
            t = tarfile.TarFile(src)
        except tarfile.ReadError:
            print("Failed. Is " + src + " an Docker image?")
            sys.exit(1)
        t.extractall(temp_dir)
        manifest_path = os.path.join(temp_dir, "manifest.json")
        with open(manifest_path, "r") as manifest_file:
            manifest_content = manifest_file.read()
            print(manifest_content)
            manifest = json.loads(manifest_content)
            manifest = manifest[-1]
            config = manifest["Config"] if "Config" in manifest else manifest["config"]
            config_f = join(temp_dir, config)
            layers = manifest["Layers"] if "Layers" in manifest else manifest["layers"]
            layers_f = [join(temp_dir, layer) for layer in layers]
        manifest = build_manifest(config_f, layers_f)
        upload_blob(repository_url, config_f, "application/vnd.docker.container.image.v1+json")
        for layer_f in layers_f:
            upload_blob(repository_url, layer_f, "application/vnd.docker.image.rootfs.diff.tar.gzip")
        upload_manifest(repository_url, manifest)
    finally:
        shutil.rmtree(temp_dir)
