import argparse
import asyncio
import os
import sys
from getpass import getpass

from crpy.common import UnauthorizedError
from crpy.registry import RegistryInfo
from crpy.storage import save_credentials


async def _pull(args):
    ri = RegistryInfo.from_url(args.url)
    await ri.pull(args.filename)


async def _push(args):
    ri = RegistryInfo.from_url(args.url)
    await ri.push(args.filename)


async def _login(args):
    if args.username is None:
        args.username = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    ri = RegistryInfo.from_url(args.url)
    await ri.auth(username=args.username, password=args.password)
    save_credentials(ri.registry, args.username, args.password)


def main(*args):
    parser = argparse.ArgumentParser(
        prog="crpy",
        description="Package that can do basic docker command like pull and push without installing the "
        "docker virtual machine",
        epilog="For reporting issues visit https://github.com/bvanelli/docker-pull-push",
    )
    parser.add_argument("-p", "--proxy", nargs=1, help="Proxy for all requests.", default=None)
    subparsers = parser.add_subparsers()
    pull = subparsers.add_parser(
        "pull",
        help="Pulls a docker image from a remove repo.",
    )
    pull.set_defaults(func=_pull)
    pull.add_argument("url", nargs="?", help="Remote repository to pull from.")
    pull.add_argument("filename", nargs="?", help="Output file for the compressed image.")

    push = subparsers.add_parser(
        "push",
        help="Pushes a docker image from a remove repo.",
    )
    push.set_defaults(func=_push)
    push.add_argument("filename", nargs="?", help="File containing the docker image to be pushed.")
    push.add_argument("url", nargs="?", help="Remote repository to push to.")

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

    arguments = parser.parse_args(args if args else None)

    # if a proxy is set, use it on env variables
    if arguments.proxy:
        os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = arguments.proxy

    try:
        if not hasattr(arguments, "func"):
            parser.print_help()
        else:
            asyncio.run(arguments.func(arguments))
    except (AssertionError, ValueError, UnauthorizedError, KeyboardInterrupt) as e:
        print(f"{e}")
        sys.exit(-1)


if __name__ == "__main__":
    main()
