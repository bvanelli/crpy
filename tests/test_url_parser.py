from crpy.auth import get_url_from_auth_header
from crpy.registry import RegistryInfo


def test_parse_registry_url():
    docker_io = RegistryInfo.from_url("index.docker.io/library/nginx")
    assert docker_io == RegistryInfo("index.docker.io", "library/nginx", "latest")

    google_io = RegistryInfo.from_url("gcr.io/distroless/cc:1.2.3")
    assert google_io == RegistryInfo("gcr.io", "distroless/cc", "1.2.3")

    # test with custom port
    localhost = RegistryInfo.from_url("localhost:5000/my/awesome/image:tag")
    assert localhost == RegistryInfo("localhost:5000", "my/awesome/image", "tag")
    localhost_short = RegistryInfo.from_url("localhost:5000/alpine:latest")
    assert localhost_short == RegistryInfo("localhost:5000", "alpine", "latest")

    # check if http is also supported
    insecure_registry = RegistryInfo.from_url("http://registry:5000/my/repository/")
    assert insecure_registry == RegistryInfo("registry:5000", "my/repository", "latest", False)

    # check if the default url is used when url is omitted. It should default to docker hubs
    alpine = RegistryInfo.from_url("alpine")
    assert str(alpine) == "index.docker.io/library/alpine:latest"
    # check if it also works when providing user specific images
    bitnami = RegistryInfo.from_url("bitnami/postgresql")
    assert str(bitnami) == "index.docker.io/bitnami/postgresql:latest"


def test_url_from_auth():
    url = get_url_from_auth_header(
        'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/nginx:pull"'
    )
    assert url == "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nginx:pull"
