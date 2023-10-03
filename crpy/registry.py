import functools
import io
import json
import os
import pathlib
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Union

from async_lru import alru_cache
from rich import print as rprint

from crpy.auth import get_token, get_url_from_auth_header
from crpy.common import (
    Platform,
    Response,
    _request,
    _stream,
    compute_sha256,
    platform_from_dict,
)
from crpy.storage import get_credentials, get_layer_from_cache, save_layer

# taken from https://github.com/davedoesdev/dxf/blob/master/dxf/__init__.py#L24
_schema1_mimetype = "application/vnd.docker.distribution.manifest.v1+json"

_schema2_mimetype = "application/vnd.docker.distribution.manifest.v2+json"
_schema2_list_mimetype = "application/vnd.docker.distribution.manifest.list.v2+json"

# OCIv1 equivalent of a docker registry v2 manifests
_ociv1_manifest_mimetype = "application/vnd.oci.image.manifest.v1+json"
# OCIv1 equivalent of a docker registry v2 "manifests list"
_ociv1_index_mimetype = "application/vnd.oci.image.index.v1+json"


# we redirect all print statements no stderr, so that piping on command line works as expected. You can then pipe the
# results to jq or similar without interfering with the logging.
print = functools.partial(rprint, file=sys.stderr)


@dataclass
class RegistryInfo:
    """
    This dataclass does all interactions with a remote registry, using async methods. You can initialize the class
    using the individual parameters, but a better way is from the `RegistryInfo.from_url(url)` method. From there, you
    can use the registry like a python object:

    >>> ri = RegistryInfo.from_url("alpine:latest")
    >>> print(await ri.get_config())

    See https://containers.gitbook.io/build-containers-the-hard-way/ for an in depth explanation of what is going on.
    """

    registry: str
    repository: str
    tag: str
    https: bool = True
    token: Optional[str] = None

    # networking options
    proxy: Optional[str] = None
    insecure: bool = False

    @property
    def _headers(self) -> dict:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @property
    def _aiohttp_kwargs(self) -> dict:
        kwargs = {}
        if self.proxy:
            kwargs["proxy"] = kwargs
        if self.insecure:
            kwargs["ssl"] = False
        return kwargs

    async def _request_with_auth(
        self,
        url: str,
        *,
        method: str = "post",
        params: dict = None,
        data: Union[dict, bytes, None] = None,
        headers: dict = None,
    ) -> Response:
        if not headers:
            headers = {}
        response = await _request(
            url,
            {**headers, **self._headers},
            params=params,
            data=data,
            method=method,
            aiohttp_kwargs=self._aiohttp_kwargs,
        )
        if response.status == 401:
            www_auth = response.headers["WWW-Authenticate"]
            await self.auth(www_auth)
            response = await _request(
                url,
                {**headers, **self._headers},
                params=params,
                data=data,
                method=method,
                aiohttp_kwargs=self._aiohttp_kwargs,
            )
            if response.status == 401:
                raise ValueError(f"Could not authenticate to registry {self}")
        return response

    def v2_url(self):
        method = "https" if self.https else "http"
        return f"{method}://{self.registry}/v2"

    def manifest_url(self, reference: Optional[str] = None):
        return f"{self.v2_url()}/{self.repository}/manifests/{reference or self.tag}"

    def blobs_url(self):
        return f"{self.v2_url()}/{self.repository}/blobs"

    def __hash__(self):
        return hash((self.registry, self.registry, self.tag, self.https))

    def __str__(self):
        if self.repository:
            return f"{self.registry}/{self.repository}:{self.tag}"
        else:
            return self.registry

    async def auth(
        self,
        www_auth: str = None,
        username: str = None,
        password: str = None,
        b64_token: str = None,
        use_config: bool = True,
    ):
        if www_auth is None:
            method = "https" if self.https else "http"
            response = await _request(
                f"{method}://{self.registry}/v2/", method="get", aiohttp_kwargs=self._aiohttp_kwargs
            )
            www_auth = response.headers["WWW-Authenticate"]
        assert www_auth.startswith('Bearer realm="')
        # check if config contains username and password we can use
        if not b64_token and use_config:
            b64_token = get_credentials(self.registry)
        # reuse this token in consecutive requests
        self.token = await get_token(
            get_url_from_auth_header(www_auth),
            username=username,
            password=password,
            b64_token=b64_token,
        )
        print(f"Authenticated at {self}")
        return self.token

    @staticmethod
    def from_url(url: str, proxy: str = None, insecure: bool = False) -> "RegistryInfo":
        """
        Generates a RegistryInfo object from an url, automatically splitting the url into the dataclass fields.

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
        # todo: validate with https://github.com/distribution/reference/blob/main/reference.go
        if "://" in url:
            scheme, url = url.split("://")
            has_scheme = True
        else:
            scheme, has_scheme = "https", False
        possibly_hub_image = (url.count("/") == 0 and "." not in url.split("/")[0]) or (  # example: alpine:latest
            url.count("/") == 1  # example: bitnami/postgres:latest
            and "." not in url.split("/")[0]  # exception: myregistry.com/alpine:latest
            and ":" not in url.split("/")[0]  # exception: localhost:5000/alpine:latest
        )
        if not has_scheme and possibly_hub_image:
            # when user provides a single word like "alpine" or "alpine:latest" or bitnami/postgresql
            registry, repository_raw = "index.docker.io", f"library/{url}" if "/" not in url else url
        else:
            registry, _, repository_raw = url.partition("/")
            if "docker.io" in registry and "/" not in repository_raw:
                # library image
                repository_raw = f"library/{repository_raw}"
        name, tag = (repository_raw.split(":") + ["latest"])[:2]
        return RegistryInfo(registry, name.strip("/"), tag, scheme == "https", proxy=proxy, insecure=insecure)

    @alru_cache
    async def get_manifest(self, fat: bool = False, reference: Optional[str] = None) -> Response:
        """
        Gets the manifest for a remote docker image. This is a JSON file containing the metadata for how the image is
        stored.
        :param fat: If it should return the manifest list, rather than the default manifest. This allows the user to
            also select multiple architectures instead of being limited in just the default one.
            See https://docs.docker.com/registry/spec/manifest-v2-2/ for explanation.
        :param reference: Reference for the manifest retrieval. If not specified, the configured tag is used as a
            default. If you are looking for the manifest for a multi-arch image, then you need to first retrieve the
            manifest by doing a fat manifest query then getting the correct reference for the architecture. Use the
            method `get_manifest_from_architecture()` for that.
        :return: Response object with status code, raw data and response headers.
        """
        base_headers = (
            _schema1_mimetype,
            _schema2_mimetype,
        )
        if fat:
            base_headers = base_headers + (
                _schema2_list_mimetype,
                _ociv1_manifest_mimetype,
                _ociv1_index_mimetype,
            )
        headers = {"Accept": ", ".join(base_headers)}
        response = await self._request_with_auth(self.manifest_url(reference), method="get", headers=headers)
        return response

    async def get_manifest_from_architecture(self, architecture: Union[str, Platform, None] = None) -> dict:
        if isinstance(architecture, Platform):
            architecture = architecture.value
        elif isinstance(architecture, str):
            # validate arch
            try:
                Platform(architecture)
            except ValueError:
                raise ValueError(
                    f"Platform '{architecture}' not recognized. Choose one from {[e.value for e in Platform]}"
                ) from None
        if architecture is not None:
            manifests = (await self.get_manifest(fat=True)).json()
            available_architectures = [platform_from_dict(manifest["platform"]) for manifest in manifests["manifests"]]
            for idx, a in enumerate(available_architectures):
                if a == architecture:
                    # the short manifest does not contain any layers, that is why we have to then re-query the API
                    # to get the full one, passing the digest as reference name.
                    short_manifest = manifests["manifests"][idx]
                    full_manifest = await self.get_manifest(reference=short_manifest["digest"])
                    return full_manifest.json()
            raise ValueError(
                f"No matching manifest for {architecture} in the manifest list entries at {self}.\n"
                f"Available architectures: {available_architectures}"
            )
        else:
            manifest = await self.get_manifest()
            return manifest.json()

    @alru_cache
    async def get_config(self, architecture: Union[str, Platform] = None) -> Response:
        """
        Gets the config of a docker image. The config contains all basic information of a docker image, including the
        entrypoints, cmd, environment variables, etc.

        :param architecture: optional architecture for the image. If not provided, the default registry architecture
            will be pulled.
        :return: Response object with status code, raw data and response headers.
        """
        manifest = await self.get_manifest_from_architecture(architecture)
        config_digest = manifest["config"]["digest"]
        response = await self._request_with_auth(
            f"{self.blobs_url()}/{config_digest}", method="get", headers=self._headers
        )
        return response

    @alru_cache
    async def get_layers(self, architecture: Union[str, Platform, None] = None) -> List[str]:
        """
        Gets the digests for each layer available at the remote registry.
        :param architecture: optional architecture for the image. If not provided, the default registry architecture
            will be pulled.
        :return:
        """
        manifest = await self.get_manifest_from_architecture(architecture)
        layers = [m["digest"] for m in manifest["layers"]]
        return layers

    async def pull_layer(
        self, layer: str, file_obj: Optional[io.BytesIO] = None, use_cache: bool = True
    ) -> Optional[bytes]:
        """
        Retrieves a layer from a remote registry.

        :param layer: reference for the layer. Looks something like "sha256:1234..."
        :param file_obj: optional file-like object to write the response.
        :param use_cache: enables the local cache, saving layers to ~/.crpy/ folder.
        :return: If a file_obj is provided, the layer is written to that file, otherwise the binary data is returned.
        """
        content = get_layer_from_cache(layer) if use_cache else None

        if content is not None:
            print(f"Using cache for layer {layer.split(':')[1][0:12]}")
            # short-circuit if the content is in the cache
            if file_obj is None:
                return content
            file_obj.write(content)
            return None

        return await self.get_content_from_remote(layer, file_obj, use_cache)

    async def get_content_from_remote(
        self, layer: str, file_obj: Optional[io.BytesIO], use_cache: bool
    ) -> Optional[bytes]:
        content = await self.get_response_content(layer, file_obj)
        if use_cache:
            save_layer(layer, content if file_obj is None else file_obj.getvalue())
        return content

    async def get_response_content(self, layer: str, file_obj: Optional[io.BytesIO]) -> bytes:
        if file_obj is None:
            response = await self._request_with_auth(f"{self.blobs_url()}/{layer}", method="get", headers=self._headers)
            return response.data
        else:
            async for chunk in _stream(
                f"{self.blobs_url()}/{layer}", self._headers, aiohttp_kwargs=self._aiohttp_kwargs
            ):
                file_obj.write(chunk)
            file_obj.seek(0)
            return file_obj.getvalue()

    async def pull(
        self, output_file: Union[str, pathlib.Path, io.BytesIO], architecture: Union[str, Platform, None] = None
    ):
        """
        Pulls an image from a remote repository. The image will be packed into a tar-file and saved to disk (or to a
        file-like object).

        :param output_file: path or file-like object to save the binary data.
        :param architecture: architecture to pull the image. If not set, the default registry architechture will be
            used.
        :return:
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"{self.tag}: Pulling from {self.registry}/{self.repository}")
            web_manifest = await self.get_manifest_from_architecture(architecture)
            config = await self.get_config(architecture)

            config_filename = f'{web_manifest["config"]["digest"].split(":")[1]}.json'
            with open(f"{temp_dir}/{config_filename}", "wb") as outfile:
                outfile.write(config.data)

            layer_path_l = []
            for layer in await self.get_layers():
                layer_folder = layer.split(":")[-1]
                path = layer_folder + "/layer.tar"
                layer_bytes = await self.pull_layer(layer, use_cache=True)
                os.makedirs(f"{temp_dir}/{layer_folder}", exist_ok=True)
                with open(f"{temp_dir}/{path}", "wb") as f:
                    f.write(layer_bytes)
                layer_path_l.append(path)
                print(f"{layer.split(':')[1][0:12]}: Pull complete")

            manifest = [{"Config": config_filename, "RepoTags": [str(self)], "Layers": layer_path_l}]
            with open(f"{temp_dir}/manifest.json", "w") as outfile:
                json.dump(manifest, outfile)

            if isinstance(output_file, io.BytesIO):
                output_kwargs = {"fileobj": output_file, "mode": "w"}
            else:
                output_kwargs = {"name": output_file, "mode": "w"}
            with tarfile.open(**output_kwargs) as tar_out:
                os.chdir(temp_dir)
                tar_out.add(".")
                os.chdir("..")  # leave the folder, otherwise it might not be able to be deleted on windows
            print(f"Downloaded image from {self}")

    async def push_layer(self, file_obj: Union[bytes, str, pathlib.Path], force: bool = False) -> Optional[dict]:
        """
        Pushes a layer to a remote repo.

        :param file_obj: file or bytes object to be pushed.
        :param force: will force the upload of the blob even when it's available at the remote. If set to false, it
            skips already pushed layers (default).
        :return: dictionary containing the fields {"size": int}, with the blob size, {"digest": str}, with the sha256
            digest and {"existing": bool}, saying if the manifest upload was skipped because it already existed.
        """
        # load layer and compute its digest
        if isinstance(file_obj, pathlib.Path) or isinstance(file_obj, str):
            with open(file_obj, "rb") as f:
                content = f.read()
        elif isinstance(file_obj, io.BytesIO):
            content = file_obj.read()
        else:
            content = file_obj
        digest = compute_sha256(content)
        manifest = {
            "size": len(content),
            "digest": digest,
        }
        # first check if a blob exists with a HEAD request
        response = await self._request_with_auth(f"{self.blobs_url()}/{digest}", method="head", headers=self._headers)
        if response.status == 200 and not force:
            # layer already exists
            manifest["existing"] = True
            return manifest
        # the process for pushing a layer is first making a request to /uploads and getting the location header
        response = await self._request_with_auth(f"{self.blobs_url()}/uploads/", method="post")
        location_header = response.headers["Location"]
        # we do a monolith upload with a single PUT requests
        response = await self._request_with_auth(
            location_header,
            params={"digest": digest},
            method="put",
            data=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status == 201, f"Failed to upload blob with digest {digest}: {response.data}"
        manifest["existing"] = False
        return manifest

    @staticmethod
    def build_manifest(
        config: dict, layers: List[dict], schema_version: int = 2, media_type: str = _schema2_mimetype
    ) -> dict:
        """
        Manifest generator, taken from:

            containers.gitbook.io/build-containers-the-hard-way/#registry-format-docker-image-manifest-v-2-schema-2

        :param config: descriptor of container configuration blob. Descriptors are JSON objects containing 3 fields:
            - mediaType: `application/vnd.docker.container.image.v1+json` for a container configuration or
                `application/vnd.docker.image.rootfs.diff.tar.gzip` for a layer
            - size: the size of the blob, in bytes
            - digest: the digest of the content
        :param layers: list of descriptors of layer blobs, in the same order as the rootfs of the container
            configuration. Follow the same blob descriptor as the config.
        :param schema_version: schema version of the manifest, default as 2
        :param media_type: manifest format version, default as `application/vnd.docker.distribution.manifest.v2+json`
        :return:
        """
        return {
            "schemaVersion": schema_version,
            "mediaType": media_type,
            "config": config,
            "layers": layers,
        }

    async def push_manifest(self, manifest: dict) -> Response:
        """
        Pushes a manifest to the remote registry. The manifest follow a standard format. Check ``self.build_manifest()``
        for details.

        :param manifest: dictionary containing the manifest.
        :return: Response from the remote endpoint.
        """
        # build the manifest here according to
        # containers.gitbook.io/build-containers-the-hard-way/#registry-format-docker-image-manifest-v-2-schema-2
        response = await self._request_with_auth(
            f"{self.manifest_url()}",
            method="put",
            data=json.dumps(manifest, indent=3).encode(),
            headers={"Content-Type": _schema2_mimetype},
        )
        assert response.status == 201
        return response

    async def push(self, input_file: Union[str, pathlib.Path, io.BytesIO]):
        """
        Pushes an input file to the remote repository. The tag that will be used is the one defined for the object. If
        no tag was provided, the default "latest" will be used. The file must be a tar-file with the config, manifest
        and gzipped layers. This can be the output from a command line ``crpy pull alpine:3.18.2`` or from the docker
        cli, for example, ``docker save alpine:3.18.2 -o alpine_3.18.2``.

        :param input_file: bytes or path to file to be uploaded.
        :return: None
        """
        try:
            if isinstance(input_file, io.BytesIO):
                t = tarfile.TarFile(fileobj=input_file)
            else:
                t = tarfile.TarFile(input_file)
        except tarfile.ReadError:
            raise ValueError(f"Failed to load {input_file}. Is an Docker image?")
        with tempfile.TemporaryDirectory() as temp_dir:
            t.extractall(temp_dir)
            manifest_path = pathlib.Path(temp_dir) / "manifest.json"
            manifest_content = manifest_path.read_text()
            manifest = json.loads(manifest_content)[-1]
            layers = manifest["Layers"] if "Layers" in manifest else manifest["layers"]

            print(f"The push refers to repository [{self}]")

            # upload config
            config = manifest["Config"] if "Config" in manifest else manifest["config"]
            config_path = pathlib.Path(temp_dir) / config
            config_manifest = await self.push_layer(config_path)
            config_manifest.pop("existing")
            config_manifest["mediaType"] = "application/vnd.docker.container.image.v1+json"

            # upload layers
            layers_manifest = []
            for layer in layers:
                layer_path = pathlib.Path(temp_dir) / layer
                layer_manifest = await self.push_layer(layer_path)
                if not layer_manifest["existing"]:
                    print(f"{layer[0:12]}: Pushed")
                else:
                    print(f"{layer[0:12]}: Layer already exists")
                layer_manifest.pop("existing")
                layer_manifest["mediaType"] = "application/vnd.docker.image.rootfs.diff.tar.gzip"
                layers_manifest.append(layer_manifest)
            # once the blobs are committed, we can push the manifest
            image_manifest = self.build_manifest(config_manifest, layers_manifest)
            r = await self.push_manifest(image_manifest)
            # some registries like docker hub return the header in lower case
            image_digest = r.headers.get("Docker-Content-Digest", "") or r.headers.get("docker-content-digest")
            print(f"Pushed {self.tag}: digest: {image_digest}")

    async def _list(self, path: str, last: str = None, n: int = None, lazy: bool = False) -> List[dict]:
        url = f"{self.v2_url()}/{path}"
        params = {}
        if n is not None:
            params["n"] = n
        if last is not None:
            params["last"] = last
        response = await self._request_with_auth(url, method="get", params=params, headers=self._headers)
        ret_value = [response.json()]
        # use pagination to get further tags, if any
        if "Link" in response.headers and not lazy:
            last = re.search(r"last=(\w+)", response.headers["Link"]).group(1)
            n = re.search(r"n=(\d+)", response.headers["Link"]).group(1)
            next_response = await self._list(path, last, int(n))
            ret_value.append(next_response[0])
        return ret_value

    async def list_repositories(self, last: str = None, n: int = None) -> List[str]:
        """
        Lists the repositories contents to show all available images. It will retrieve all pages, unless lazy is
        specified. In order to list, the user token must have the appropriate permissions.

        :param last: Last element received on the previous page, in case of a paged call. ``None`` means from beginning.
        :param n: Number of elements on each page. ``None`` means default from registry. If a number is provided, the
            endpoint will then paginate the response with this size. It is necessary to then make the next call using
            the last element of the previous response.
        :return: List of repositories available in the registry.
        """
        response = await self._list("_catalog", last, n, False if n is None else True)
        return [entry for page in response for entry in page["repositories"]]

    async def list_tags(self, last: str = None, n: int = None) -> List[str]:
        """
        Lists the tags available for the repository. It will retrieve all pages, unless lazy is
        specified. In order to list, the user token must have the appropriate permissions.

        :param last: Last element received on the previous page, in case of a paged call. ``None`` means from beginning.
        :param n: Number of elements on each page. ``None`` means default from registry. If a number is provided, the
            endpoint will then paginate the response with this size. It is necessary to then make the next call using
            the last element of the previous response.
        :return: List of tags available in the repository.
        """
        response = await self._list(f"{self.repository}/tags/list", last, n, False if n is None else True)
        return [entry for page in response for entry in page["tags"]]

    async def delete_tag(self) -> Response:
        """
        Deletes a tag from a repository.

        This endpoint does for all container registries (an example in docker hub), as the API can return
        {"code":"UNSUPPORTED"}. If you are using a private registry, the environment variable
        REGISTRY_STORAGE_DELETE_ENABLED=true has to be set in order to enable tag deletion.

        :return: Response from the endpoint
        """
        # according to the docs, we first need to retrieve the reference, as you can't delete by tags
        manifest = await self.get_manifest()
        # get the docker content digest
        reference = manifest.headers["docker-content-digest"]
        url = f"{self.v2_url()}/{self.repository}/manifests/{reference}"
        response = await self._request_with_auth(url, headers=self._headers, method="delete")
        return response
