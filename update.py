import render
import scan

import argparse
import os
import subprocess
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('commands', nargs='*')
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('credentials.yaml') as fp:
        creds = yaml.safe_load(fp)

    if not args.commands or 'scan' in args.commands:
        scan.main([])

    if not args.commands or 'render' in args.commands:
        render.main([])

    if not args.commands or 'upload' in args.commands:
        subprocess.run([
            'rsync', '-ru', 'output/*', creds['ssh_target']
        ], shell=True, check=True)

if __name__ == "__main__":
    main()