import io
import pathlib
import tempfile
import sys
import os
import shutil
import tarfile
import json
from http.client import HTTPConnection, HTTPSConnection
from typing import Union
from crpy.auth import get_token, get_url_from_auth_header
from crpy.utils import RegistryInfo
from crpy.storage import get_config_dir


def get(url, headers_req: dict = None):
    if not headers_req:
        headers_req = {}
    print(f"GET {url}, headers = {str(list(headers_req))}")
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
        # Only one auth mechanism allowed; only the X-Amz-Algorithm query parameter,
        # Signature query string parameter or the Authorization header should be specified
        del headers_req["Authorization"]
        response = requests.get(headers["location"], headers=headers_req)
        return {
            "status": response.status_code,
            "headers": headers_req,
            "content": response.content,
        }
    else:
        return {"status": status, "headers": headers, "content": r.read()}


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


def pull_tar_gz(cache_dir: pathlib.Path, url: str, name: str, path: str):
    """
    Get a layer in a compressed format, and saves it locally (unzipped).
    The tar name is expected to contain a hash, thus to be cacheable.
    """
    cache_name = cache_dir / name.replace(":", "_")
    # make sure the request sha is not already present on cache
    if not os.path.exists(cache_name):
        response = pull(f"{url}/{name}")["content"]
        with open(cache_name, mode="wb") as localfile:
            localfile.write(response)
            shutil.move(cache_name, cache_name)

    os.makedirs(path[: path.rfind("/")])
    shutil.copyfile(cache_name, path)


def pull_image(image_url: str, output_file: Union[str, pathlib.Path, io.BytesIO]):
    args = RegistryInfo.from_url(image_url)
    cache_dir = get_config_dir()
    with tempfile.TemporaryDirectory() as temp_dir:
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
                cache_dir,
                args.blobs_url(),
                layer["digest"],
                temp_dir + "/" + path,
            )
            layer_path_l.append(path)

        manifest = [{"Config": config_filename, "RepoTags": [], "Layers": layer_path_l}]
        with open(temp_dir + "/" + "manifest.json", "w") as outfile:
            json.dump(manifest, outfile)

        if isinstance(output_file, io.BytesIO):
            output_kwargs = dict(fileobj=output_file, mode="w")
        else:
            output_kwargs = dict(name=output_file, mode="w")
        with tarfile.open(**output_kwargs) as tar_out:
            os.chdir(temp_dir)
            tar_out.add(".")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("docker-pull fullname target")
        print("  Example: docker-pull index.docker.io/library/alpine my-image")
        exit(1)

    pull_image(sys.argv[1], sys.argv[2])
