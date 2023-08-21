import io
import tarfile

import pytest

from crpy.docker_pull import pull_image
from crpy.utils import Platform, RegistryInfo, compute_sha256


def test_pull_docker_io():
    file = io.BytesIO()
    pull_image("index.docker.io/library/alpine:3.18.2", file)
    file.seek(0)
    with tarfile.open(fileobj=file, mode="r") as tf:
        content = tf.getnames()
        assert "./manifest.json" in content
        # make sure one layer is in
        assert len([layer for layer in content if layer.endswith("layer.tar")])


@pytest.mark.asyncio
async def test_api_calls():
    ri = RegistryInfo.from_url("index.docker.io/library/alpine:3.18.2")
    fat_manifest = (await ri.get_manifest(fat=True)).json()
    manifest = (await ri.get_manifest()).json()
    assert manifest["config"]["digest"] == "sha256:c1aabb73d2339c5ebaa3681de2e9d9c18d57485045a4e311d9f8004bec208d67"
    # the digest of the fat manifest should match the one in
    # https://hub.docker.com/layers/library/alpine/3.18.2/images/
    # sha256-25fad2a32ad1f6f510e528448ae1ec69a28ef81916a004d3629874104f8a7f70
    assert (
        fat_manifest["manifests"][0]["digest"]
        == "sha256:25fad2a32ad1f6f510e528448ae1ec69a28ef81916a004d3629874104f8a7f70"
    )
    manifest_linux = await ri.get_manifest_from_architecture(Platform.LINUX)
    assert manifest_linux == fat_manifest["manifests"][0]

    config = await ri.get_config()
    assert config.json()["config"]["Cmd"][0] == "/bin/sh"

    layers = await ri.get_layers()
    assert layers == ["sha256:31e352740f534f9ad170f75378a84fe453d6156e40700b882d737a8f4a6988a3"]

    image_layer = await ri.pull_layer(layers[0])
    sha_256_layer = compute_sha256(image_layer)
    assert sha_256_layer == layers[0]
