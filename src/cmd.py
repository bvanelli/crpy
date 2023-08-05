import argparse
import sys


def _pull(args):
    pass

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
    pull.add_argument("url", nargs=1, help="Remote repository to pull from.")

    push = subparsers.add_parser(
        "push",
        help="Pulls a docker image from a remove repo.",
    )
    push.set_defaults(func=_push)
    push.add_argument("filename", nargs=1, help="File containing the docker image to be pushed.")
    push.add_argument("url", nargs=1, help="Remote repository to push to.")

    arguments = parser.parse_args()

    try:
        if not hasattr(arguments, "func"):
            parser.print_help()
        else:
            arguments.func(arguments)
    except (AssertionError, ValueError, KeyboardInterrupt) as e:
        print(f"{e}")
        # remove file in case of error
        sys.exit(-1)
