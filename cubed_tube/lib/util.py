"""
util.py - Collection of convenience funcitons
"""

from datetime import datetime
import hashlib
from typing import Optional, Union, Dict, cast, TypeVar, Callable
import yaml

from cubed_tube.lib import schema


T = TypeVar('T')


def chunk(items, count, chunk_size):
    """Chunk a given sequence into smaller lists"""
    for i in range(0, count, chunk_size):
        yield items[i:i+chunk_size]


def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()


def cache_func(func: Callable[[], T]) -> T:
    """Decorator which caches a zero-argument function"""
    func._cache_dt = None
    func._cache_value = None
    func._test_data = None
    def wrapper(ttl: int=0, now: datetime=None, _test_data=None):
        now = now or datetime.now()
        if _test_data is not None:
            func._test_data = _test_data
            return _test_data
        if func._test_data is not None:
            return func._test_data
        if func._cache_dt:
            if not ttl or (now - func._cache_dt).total_seconds() < ttl:
                return func._cache_value
        func._cache_value = func()
        func._cache_dt = now
        return func._cache_value
    return wrapper


@cache_func
def load_credentials() -> schema.Credentials:
    """Loads the credentials (secrets) file"""
    with open('credentials.yaml') as fp:
        return schema.Credentials.from_dict(yaml.safe_load(fp))


@cache_func
def load_config() -> schema.Configuration:
    """Loads the playlists (configuration) file"""
    with open('playlists.yaml') as fp:
        return schema.Configuration.from_dict(yaml.safe_load(fp))

def ensure_str(text: Union[str,bytes], encoding='utf-8'):
    """An equivalent to six.ensure_str."""
    if type(text) is bytes:
        return cast(bytes, text).decode(encoding)
    return text
