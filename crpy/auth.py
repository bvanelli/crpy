import requests
from base64 import b64encode
from functools import lru_cache


@lru_cache
def get_token(
    url: str,
    username: str = None,
    password: str = None,
    b64_token: str = None,
):
    # get the credentials here.
    # I'll use the simple auth since it mostly works
    headers = {}
    if username and password:
        username, password = "", ""
        token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
    elif b64_token:
        headers = {"Authorization": f"Basic {b64_token}"}
    token_req = requests.get(url, headers=headers)
    token_req.raise_for_status()
    req_json = token_req.json()
    if "token" in req_json:
        return req_json["token"]
    elif "access_token" in req_json:
        return req_json["access_token"]
    else:
        raise ValueError(f"Authentication is required and it was not provided: {req_json}")


def get_url_from_auth_header(h: str):
    """
    >>> get_url_from_auth_header('Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/nginx:pull"')
    'https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nginx:pull'
    """
    start_key = 'Bearer realm="'
    assert h.startswith(start_key)
    out = h.lstrip(start_key).replace('",', "?", 1).replace('",', "&").replace('="', "=").rstrip('"')
    return out
