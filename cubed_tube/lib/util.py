"""
util.py - Collection of convenience funcitons
"""

from datetime import datetime
import hashlib
from typing import Union, Dict
import yaml

from cubed_tube.lib import schema


_config_file_cache: Dict[str, tuple[datetime, schema.Schema]] = {}


def chunk(items, count, chunk_size):
    """Chunk a given sequence into smaller lists"""
    for i in range(0, count, chunk_size):
        yield items[i:i+chunk_size]


def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()


def load_credentials(ttl: int=0) -> schema.Credentials:
    """Loads the credentials (secrets) file"""
    return _load_config_file('credentials.yaml', schema.Credentials, ttl)


def load_config(ttl: int=0) -> schema.Configuration:
    """Loads the playlists (configuration) file"""
    return _load_config_file('playlists.yaml', schema.Configuration, ttl)


def _load_config_file(
        file: str, _type: schema.Schema, ttl: int) -> schema.Schema:
    now = datetime.now()
    if file in _config_file_cache:
        dt, obj = _config_file_cache[file]
        if not ttl or (now - dt).total_seconds() < ttl:
            return obj
    with open(file) as fp:
        obj = _type.from_dict(yaml.safe_load(fp))
        _config_file_cache[file] = (now, obj)
    return _config_file_cache[file][1]
