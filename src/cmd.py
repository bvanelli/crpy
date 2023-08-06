import argparse
import asyncio
import sys
from src.utils import RegistryInfo


async def _pull(args):
    ri = RegistryInfo.from_url(args.url)
    await ri.pull(args.filename)


def _push(args):
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="pydocker",
        description="Package that can do basic docker command like pull and push without installing the "
                    "docker virtual machine",
        epilog="For reporting issues visit https://github.com/bvanelli/docker-pull-push",
    )
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

    arguments = parser.parse_args()

    try:
        if not hasattr(arguments, "func"):
            parser.print_help()
        else:
            asyncio.run(arguments.func(arguments))
    except (AssertionError, ValueError, KeyboardInterrupt) as e:
        print(f"{e}")
        # remove file in case of error
        sys.exit(-1)
