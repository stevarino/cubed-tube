import argparse
import os
import os.path

from cubed_tube.frontend import render
from cubed_tube.scraper import scraper


def run_wsgi_server(args):
    from cubed_tube.backend import app
    app.run(debug=True, use_reloader=False)


def run_worker(args):
    from cubed_tube.worker.worker import loop
    loop()


def run_compress(args):
    from cubed_tube.lib.trends import compress_trends
    compress_trends([
        # after 1 week, keep hourly
        (7 * 24 * 3600, 3600),
        # after 1 month, keep daily
        (30 * 24 * 3600, 24 * 3600),
    ])


def print_site_name(args):
    from cubed_tube.lib import util
    print(util.load_credentials().site_name)


SUBCOMMANDS = {
    'frontend': render,
    'scraper': scraper,
    'backend': run_wsgi_server,
    'worker': run_worker,
    'compress': run_compress,
    'site_name': print_site_name,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', '-d',  help='Work directory for configuration/output')
    subparsers = parser.add_subparsers(dest='subparser')

    for name, module in list(SUBCOMMANDS.items()):
        subparser = subparsers.add_parser(name)
        if hasattr(module, 'build_argparser'):
            SUBCOMMANDS[name] = module.main
            module.build_argparser(subparser)

    args = parser.parse_args()
    if not args.subparser:
        parser.print_help()
    elif args.subparser in SUBCOMMANDS:
        if args.directory:
            os.chdir(args.directory)
        SUBCOMMANDS[args.subparser](args)
    else:
        raise ValueError(f'Unrecognized argument: {args.subparser}')

if __name__ == "__main__":
    main()
