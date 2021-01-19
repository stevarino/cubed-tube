import argparse
import os
import os.path

from hermit_tube import scan, render

SUBCOMMANDS = {
    'scan': scan,
    'render': render,
}

def main(args: argparse.Namespace):
    if args.subparser == 'wsgi':
        from hermit_tube.lib.wsgi import app
        app.run(debug=True, use_reloader=False)
    if args.subparser in SUBCOMMANDS:
        SUBCOMMANDS[args.subparser].main(args)

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='subparser')

    wsgi_parser = subparsers.add_parser('wsgi')
    for name, module in SUBCOMMANDS.items():
        subparser = subparsers.add_parser(name)
        module.build_argparser(subparser)

    main(parser.parse_args())
