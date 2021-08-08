#!/usr/bin/python

"""
deploy.py - Increments version numbers, builds packages, and deploys to pypi.

This file anticipates a json file in the root directory. This is not tracked
in git to avoid "version bump" style commits (TODO: move file to cloud/server
somewhere?). The file format is as follows:

{
  "current": "0.1.12dev4",
  "dev": {
    "label": "dev",
    "version": [0, 1, 12, 4]
  },
  "master": {
    "version": [0, 1, 11]
  }
}

Other prerelease processes should be possible, but dev is enough for me. This
also works to keep dev/master versioning aligned.
"""


import argparse
import json
import glob
import sys
import time
import os

from pygit2 import Repository
import build.__main__ as build
import twine.__main__ as twine

def formatter(version: list[int]):
    output = '.'.join(str(x) for x in version[0:3])
    if versions[branch].get('label'):
        output += versions[branch]['label'] + str(version[3])
    return output

parser = argparse.ArgumentParser()
parser.add_argument('--major', action='store_true')
parser.add_argument('--minor', action='store_true')
parser.add_argument('--patch', action='store_true')
parser.add_argument('--increment', action='store_true', help='Increment version')
parser.add_argument('--keep', action='store_true', help='Do not delete old packages')
parser.add_argument('--build', action='store_true', help='Run build util')
parser.add_argument('--deploy', action='store_true', help='Upload packags')
args = parser.parse_args()

repo = Repository('.')
branch = repo.head.name.split('/')[-1]

print(f'Working from branch {branch}')

with open('versions.json', 'r') as fp:
    versions = json.load(fp)

if branch not in versions:
    print('Branch not recognized')
    sys.exit(1)

version = versions[branch]['version']
master = versions['master']['version']
prev = versions[branch].get('prev')
current = formatter(version)

if branch != 'master' and  tuple(master) >= tuple(version[0:3]):
    for i, n in enumerate(master):
        version[i] = master[i]
    version[-1] = 0
    version[-2] += 1


def inc(version: list[int], index: int):
    version[index] += 1
    for i in range(index+1, len(version)):
        version[i] = 0

if args.increment:
    if args.major:
        inc(version, 0)
    elif args.minor:
        inc(version, 1)
    elif args.minor:
        inc(version, 2)
    else:
        inc(version, len(version)-1)

str_version = formatter(version)
if str_version != current:
    versions[branch]['prev'] = current
versions['current'] = str_version

print(f'{versions[branch].get("prev", "?")} -> {versions["current"]}')

for i in range(3):
    print(f'\r  {3-i}!', end='')
    for i in range(10):
        print('.', end='')
        sys.stdout.flush()
        time.sleep(0.1)
    print('\r' + (' '*20), end='')
print('\nLet\'s Go!')

with open('versions.json', 'w') as fp:
    fp.write(json.dumps(versions, indent=2))

if not args.keep:
    for filename in glob.glob('dist/*'):
        os.remove(filename)

if args.build:
    build.main([])

if args.deploy:
    sys.argv = ['', 'upload', '-r', 'cubedtube', 'dist/*']
    twine.main()
