import argparse
import asyncio
import json
import os
import sys
from getpass import getpass

from rich import print
from rich.table import Table

from crpy.common import HTTPConnectionError, UnauthorizedError
from crpy.registry import RegistryInfo
from crpy.storage import (
    decode_credentials,
    get_config,
    remove_credentials,
    save_credentials,
)


async def _pull(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    filename = args.filename
    if not filename:
        # make file name compatible
        filename = ri.repository.replace(":", "_").replace("/", "_")
    await ri.pull(filename)


async def _push(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    await ri.push(args.filename[0])


async def _login(args):
    if args.username is None:
        args.username = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    ri = RegistryInfo.from_url(args.url, proxy=args.proxy, insecure=args.insecure)
    await ri.auth(username=args.username, password=args.password)
    save_credentials(ri.registry, args.username, args.password)


async def _logout(args):
    ri = RegistryInfo.from_url(args.url)
    assert not ri.repository, (
        "Invalid url provided. Please provide the full registry url, without repository name.\n"
        "   Example: [bold]index.docker.io[/bold] instead of [bold]index.docker.io/library/alpine[/bold]\n"
        "            [bold]http://localhost:5000[/bold] instead of [bold]localhost:5000[/bold]"
    )
    if remove_credentials(ri.registry):
        print(f"Removed credentials for {ri.registry}")
    else:
        raise ValueError(f"Could find find credentials for {ri.registry}")


async def _inspect_manifest(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    manifest = await ri.get_manifest_from_architecture()
    print(manifest)


async def _inspect_config(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    raw_config = await ri.get_config()
    config = json.loads(raw_config.data)
    if not args.short:
        print(config)
    else:
        for entry in config["history"]:
            print(entry["created_by"])


async def _inspect_layer(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    layers = await ri.get_layers()
    ref = args.layer_reference[0]
    try:
        ref_int = int(ref)
        layer = layers[ref_int]
        sys.stdout.buffer.write(await ri.pull_layer(layer))
    except ValueError:
        for layer in layers:
            if ref in layer:
                sys.stdout.buffer.write(await ri.pull_layer(layer))
                break


async def _repositories(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    for entry in await ri.list_repositories():
        print(entry)


async def _tags(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    if not ri.repository:
        raise ValueError("Repository must be provided to list tags!")
    for entry in await ri.list_tags():
        print(entry)


async def _delete(args):
    ri = RegistryInfo.from_url(args.url[0], proxy=args.proxy, insecure=args.insecure)
    if not ri.repository:
        raise ValueError("Repository must be provided to list tags!")
    r = await ri.delete_tag()
    print(r.data)


async def _auth(args):
    config = get_config()

    table = Table(title="Saved credentials", title_style="bold")
    table.add_column("Index", style="blue")
    table.add_column("Url", style="cyan", no_wrap=True)
    table.add_column("Username", style="magenta")
    table.add_column("Password", style="green")
    for idx, (url, entry) in enumerate(config["auths"].items()):
        username, password = decode_credentials(entry["auth"])
        if not args.show_passwords:
            password = f"{password[0:2]}***{password[-2:]}"
        table.add_row(str(idx), url, username, password)
    print(table)


def main(*args):
    parser = argparse.ArgumentParser(
        prog="crpy",
        description="Package that can do basic docker command like pull and push without installing the "
        "docker virtual machine",
        epilog="For reporting issues visit https://github.com/bvanelli/crpy",
    )
    parser.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="Use insecure registry. Ignores the validation of the certificate (useful for development registries).",
        default=False,
    )
    parser.add_argument(
        "-p",
        "--proxy",
        nargs=1,
        help="Proxy for all requests. If your proxy contains authentication, pass it on the request in the usual "
             "format \"http://user:pass@some.proxy.com\"",
        default=None,
    )
    subparsers = parser.add_subparsers()
    pull = subparsers.add_parser(
        "pull",
        help="Pulls a docker image from a remove repo.",
    )
    pull.set_defaults(func=_pull)
    pull.add_argument("url", nargs=1, help="Remote repository to pull from.")
    pull.add_argument("filename", nargs="?", help="Output file for the compressed image.")

    push = subparsers.add_parser(
        "push",
        help="Pushes a docker image from a remove repo.",
    )
    push.set_defaults(func=_push)
    push.add_argument("filename", nargs=1, help="File containing the docker image to be pushed.")
    push.add_argument("url", nargs=1, help="Remote repository to push to.")

    # authentication
    login = subparsers.add_parser("login", help="Logs in on a remote repo")
    login.set_defaults(func=_login)
    login.add_argument(
        "url",
        nargs="?",
        help="Remote repository to login to. If no registry server is specified, the default used.",
        default="index.docker.io",
    )
    login.add_argument("--username", "-u", nargs="?", help="Username", default=None)
    login.add_argument("--password", "-p", nargs="?", help="Password", default=None)

    logout = subparsers.add_parser("logout", help="Logs out of a remote repo")
    logout.add_argument("url", nargs="?", help="Remote repository to logout from.", default="index.docker.io")
    logout.set_defaults(func=_logout)

    auth = subparsers.add_parser("auth", help="Shows authenticated repositories")
    auth.add_argument(
        "--show-passwords",
        "-s",
        action="store_true",
        default=False,
        help="If the password or token should be shown in clear text.",
    )
    auth.set_defaults(func=_auth)

    # manifest
    manifest = subparsers.add_parser("manifest", help="Inspects a docker registry metadata.")
    manifest.add_argument("url", nargs=1, help="Remote repository url.")
    manifest.set_defaults(func=_inspect_manifest)
    # config
    config = subparsers.add_parser("config", help="Inspects a docker registry metadata.")
    config.add_argument("url", nargs=1, help="Remote repository url.")
    config.set_defaults(func=_inspect_config, short=False)
    # commands
    commands = subparsers.add_parser(
        "commands",
        help="Inspects a docker registry build commands. "
        "These are the same as when you check individual image layers on Docker hub.",
    )
    commands.add_argument("url", nargs=1, help="Remote repository url.")
    commands.set_defaults(func=_inspect_config, short=True)
    # layer
    layer = subparsers.add_parser("layer", help="Inspects a docker registry layer.")
    layer.add_argument("url", nargs=1, help="Remote repository url.")
    layer.add_argument(
        "layer_reference",
        nargs=1,
        help="Integer representing the layer position, full or partial hash.",
    )
    layer.set_defaults(func=_inspect_layer)
    # repositories and tags
    repositories = subparsers.add_parser("repositories", help="List the repositories on the registry.")
    repositories.add_argument("url", nargs=1, help="Remote repository url.")
    repositories.set_defaults(func=_repositories)
    tags = subparsers.add_parser("tags", help="List the tags on a repository.")
    tags.add_argument("url", nargs=1, help="Remote repository url.")
    tags.set_defaults(func=_tags)
    # delete tag
    delete = subparsers.add_parser("delete", help="Deletes a tag in a remote repo.")
    delete.add_argument(
        "url",
        nargs=1,
        help="Remote repository to login to. If no registry server is specified, the default used.",
        default="index.docker.io",
    )
    delete.set_defaults(func=_delete)

    arguments = parser.parse_args(args if args else None)

    # if a proxy is set, use it on env variables
    if arguments.proxy:
        os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = arguments.proxy

    try:
        if not hasattr(arguments, "func"):
            parser.print_help()
        else:
            asyncio.run(arguments.func(arguments))
    except (AssertionError, ValueError, UnauthorizedError, HTTPConnectionError, KeyboardInterrupt) as e:
        print(f"[red]{e}[red]", file=sys.stderr)
        sys.exit(-1)


if __name__ == "__main__":
    main()
