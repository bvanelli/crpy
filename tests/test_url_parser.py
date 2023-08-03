from src.docker_pull import RegistryInfo


def test_parse_registry_url():
    docker_io = RegistryInfo.from_url("index.docker.io/library/nginx")
    assert docker_io == RegistryInfo("index.docker.io", "library/nginx", "latest")

    google_io = RegistryInfo.from_url("gcr.io/distroless/cc:1.2.3")
    assert google_io == RegistryInfo("gcr.io", "distroless/cc", "1.2.3")
