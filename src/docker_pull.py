from dataclasses import dataclass
from functools import lru_cache
from tempfile import mkdtemp
import sys
import os
import shutil
import tarfile
import json
from http.client import HTTPConnection, HTTPSConnection
from base64 import b64encode


@dataclass
class RegistryInfo:
    registry: str
    repository: str
    tag: str
    https: bool = True

    def manifest_url(self):
        return f"https://{self.registry}/v2/{self.repository}/manifests/{self.tag}"

    def blobs_url(self):
        return f"https://{self.registry}/v2/{self.repository}/blobs/"

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
        registry, repository_raw = url.split("/", 1)
        name, tag = (repository_raw.split(":") + ["latest"])[:2]
        return RegistryInfo(registry, name, tag)


def get(url, headers_req={}):
    print("GET " + url)
    print("    headers = " + str(list(headers_req)))
    protocol = url.split("//")[0]
    host_path = url.split("//")[1]
    host = host_path.split("/")[0]
    path = host_path[len(host) :]
    # print(protocol, host, path)
    h = HTTPSConnection(host) if protocol else HTTPConnection(host)
    h.request("GET", path, None, headers_req)
    import requests

    r = h.getresponse()

    if hasattr(r, "headers"):  # Python 3
        headers = dict((k.lower(), v) for k, v in dict(r.headers).items())
    else:  # Python 2
        headers = dict(r.getheaders())
    status = int(r.status)

    if status == 307 or status == 301:
        # If sent, it sometimes triggers an error 400:
        # Only one auth mechanism allowed; only the X-Amz-Algorithm query parameter, Signature query string parameter or the Authorization header should be specified
        del headers_req["Authorization"]
        response = requests.get(headers["location"], headers=headers_req)
        return {
            "status": response.status_code,
            "headers": headers_req,
            "content": response.content,
        }
    else:
        return {"status": status, "headers": headers, "content": r.read()}


def get_url_from_auth_header(h):
    """
    >>> get_url_from_auth_header('Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/nginx:pull"')
    'https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nginx:pull'
    """
    start_key = 'Bearer realm="'
    assert h.startswith(start_key)
    h_stripped = h[len(start_key) :]
    out = h_stripped.replace('",', "?", 1)
    out = out.replace('",', "&").replace('="', "=")
    return out.rstrip('"')


@lru_cache
def get_token(url, username: str = None, password: str = None):
    # get the credentials here.
    # I'll use the simple auth since it mostly works
    headers = {}
    if username and password:
        username, password = "", ""
        token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
    token_req = get(url, headers)["content"].decode()
    req_json = json.loads(token_req)
    if "token" in req_json:
        return req_json["token"]
    elif "access_token" in req_json:
        return req_json["access_token"]
    else:
        raise ValueError(f"Authentication is required and it was not provided: {req_json}")


def pull(path: str, token=None):
    headers = {} if token is None else {"Authorization": "Bearer " + token}
    headers["Accept"] = "application/vnd.docker.distribution.manifest.v2+json"
    req = get(path, headers)
    if req["status"] == 401:
        www_auth = req["headers"]["www-authenticate"]
        assert www_auth.startswith('Bearer realm="')
        token = get_token(get_url_from_auth_header(www_auth))
        return pull(path, token)
    else:
        assert req["status"] == 200, str(req["status"]) + ": " + str(req["content"])
        return req


def pull_json(url, token=None):
    req = pull(url, token)
    return json.loads(req["content"].decode())


def pull_tar_gz(cache_dir, url, name, path):
    """
    Get a layer in a compressed format, and saves it locally (unzipped).
    The tar name is expected to contain a hash, thus to be cacheable.
    """
    cache_name = cache_dir + name.replace(":", "_")
    if not os.path.exists(cache_name):
        response = pull(url + name)["content"]
        with open(cache_name, mode="wb") as localfile:
            localfile.write(response)
            shutil.move(cache_name, cache_name)

    os.makedirs(path[: path.rfind("/")])
    shutil.copyfile(cache_name, path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("docker-pull fullname target")
        print("  Example: docker-pull index.docker.io/library/alpine my-image")
        exit(1)

    CACHE_DIR_ROOT = os.path.expanduser("~")
    assert os.path.isdir(CACHE_DIR_ROOT)
    CACHE_DIR = CACHE_DIR_ROOT + "/.docker-pull-layers-cache/"

    if not os.path.exists(CACHE_DIR):
        print("Creating cache directory: " + CACHE_DIR)
        os.makedirs(CACHE_DIR)

    try:
        temp_dir = mkdtemp()
        args = RegistryInfo.from_url(sys.argv[1])
        web_manifest = pull_json(args.manifest_url())
        config_digest = web_manifest["config"]["digest"]
        config = pull_json(f"{args.blobs_url()}/{config_digest}")

        config_filename = config_digest.split(":")[1] + ".json"
        with open(temp_dir + "/" + config_filename, "w") as outfile:
            json.dump(config, outfile)

        layer_path_l = []
        for layer in web_manifest["layers"]:
            path = layer["digest"].split(":")[-1] + "/layer.tar"
            pull_tar_gz(
                CACHE_DIR,
                args.blobs_url(),
                layer["digest"],
                temp_dir + "/" + path,
            )
            layer_path_l.append(path)

        manifest = [{"Config": config_filename, "RepoTags": [], "Layers": layer_path_l}]
        with open(temp_dir + "/" + "manifest.json", "w") as outfile:
            json.dump(manifest, outfile)

        with tarfile.open(sys.argv[2], "w") as tar_out:
            os.chdir(temp_dir)
            tar_out.add(".")
    finally:
        shutil.rmtree(temp_dir)
