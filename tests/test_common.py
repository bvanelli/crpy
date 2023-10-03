from crpy.common import Platform


def test_platform_properties():
    p = Platform("linux/amd64")
    assert p.os == "linux"
    assert p.architecture == "amd64"
    assert p.variant is None

    p_mac = Platform.from_dict({"architecture": "arm64", "os": "linux", "variant": "v8"})
    assert p_mac.variant == "v8"
