"""
util.py - Collection of convenience funcitons
"""

from datetime import datetime, timedelta
import hashlib
import os.path
from typing import Union
import yaml

from hermit_tube.lib import schema

def root(*paths):
    """Returns a path relative to the root of the app"""
    path = os.path.abspath(__file__).replace('\\', '/')
    while 'hermit_tube/lib' in path:
        path = os.path.dirname(path).replace('\\', '/')
    return os.path.join(path, *paths)


def chunk(items, count, chunk_size):
    """Chunk a given sequence into smaller lists"""
    for i in range(0, count, chunk_size):
        yield items[i:i+chunk_size]


def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()

def load_credentials(ttl: timedelta=None) -> schema.Credentials:
    """Loads the credentials (secrets) file"""
    return _load_config_file('credentials.yaml', schema.Credentials, ttl)

def load_config(ttl: timedelta=None) -> schema.Playlist:
    """Loads the playlists (configuration) file"""
    return _load_config_file('playlists.yaml', schema.Playlist, ttl)

_config_file_cache: dict[str, tuple[datetime, schema.Schema]] = {}

def _load_config_file(
        file: str, _type: schema.Schema, ttl: timedelta) -> schema.Schema:
    now = datetime.now()
    if file in _config_file_cache:
        dt, obj = _config_file_cache[file]
        if not ttl or now - dt < ttl:
            return obj
    with open(root(file)) as fp:
        obj = _type.from_dict(**yaml.safe_load(fp))
        _config_file_cache[file] = (now, obj)
    return _config_file_cache[file][1]
