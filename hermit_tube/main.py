import argparse
import os
import os.path

from hermit_tube.lib import scan, render

def run_wsgi_server(args):
    from hermit_tube.lib.wsgi import app
    app.run(debug=True, use_reloader=False)

def run_tests(args):
    import unittest
    from hermit_tube import test
    unittest.main()

SUBCOMMANDS = {
    'scan': scan,
    'render': render,
    'wsgi': run_wsgi_server,
    'test': run_tests,
}

def main(args: argparse.Namespace):
    if args.subparser in SUBCOMMANDS:
        SUBCOMMANDS[args.subparser](args)
    else:
        raise ValueError(f'Unrecognized argument: {args.subparser}')

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='subparser')

    for name, module in list(SUBCOMMANDS.items()):
        subparser = subparsers.add_parser(name)
        if hasattr(module, 'build_argparser'):
            SUBCOMMANDS[name] = module.main
            module.build_argparser(subparser)

    main(parser.parse_args())
