import io
import tarfile

from src.docker_pull import pull_image


def test_pull_docker_io():
    file = io.BytesIO()
    pull_image("index.docker.io/library/alpine:3.18.2", file)
    file.seek(0)
    with tarfile.open(fileobj=file, mode="r") as tf:
        content = tf.getnames()
        assert "./manifest.json" in content
        # make sure one layer is in
        assert len([layer for layer in content if layer.endswith("layer.tar")])
