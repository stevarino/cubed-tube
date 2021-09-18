"""
util.py - Collection of convenience funcitons
"""

from collections import defaultdict
from datetime import datetime
from functools import cache
import hashlib
import random
from typing import Optional, Union, Dict, cast, TypeVar, Callable, List, Tuple, Any
import yaml

import jsonpath_ng
from prometheus_client import Counter

from cubed_tube.lib import schemas


T = TypeVar('T')


class Timer:
    """An overengineered Timer class that returns True if ttl has expired"""
    def __init__(self, default_ttl: int = None) -> None:
        self.default_ttl = default_ttl
        self.dt: datetime = None
        self.mult: float = 1.0

    def is_ready(self, ttl: int = None, reset: bool = True,
                 now: datetime = None, jitter=0.1):
        now = now or datetime.now()
        ttl = ttl if ttl is not None else self.default_ttl

        if not ttl:
            return False

        if ttl > 0 and self.dt is not None:
            if self.mult * (now - self.dt).total_seconds() < ttl:
                return False

        if reset:
            self.mult = random.random() * 2 * jitter + 1 - jitter
            self.dt = now
        return True
    
    def reset(self, now: datetime = None):
        self.dt = now or datetime.now()


def make_counter(name: str, desc: str, labelnames: Optional[List[str]] = None,
                 labelshape: Optional[List[Tuple]] = None
                ) -> Counter:
    """
    Creates a counter, initializing it at zero
    
    labelnames is a list of strings, as Counter() expectes.
    
    labelshapes is a list of tuples of label values, allowing for non-uniform
    shaping of labels. Consider using itertools.product for a uniform shaping
    if desired.
    """
    if not labelnames:
        cnt = Counter(name, desc)
        cnt.inc(0)
        return cnt
    cnt = Counter(name, desc, labelnames=labelnames)
    for shape in labelshape:
        cnt.labels(**dict(zip(labelnames, shape))).inc(0)
    return cnt


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
    func._value = None
    func._test_value = None
    func._is_set = False
    func._timer = Timer()

    def wrapper(ttl: int=0, now: datetime=None, _test_value=None, jitter=0.1):
        now = now or datetime.now()
        if _test_value is not None:
            func._test_value = _test_value
        if func._test_value is not None:
            return func._test_value

        if func._is_set and not func._timer.is_ready(
                ttl, reset=False, now=now, jitter=jitter):
            return func._value
        func._value = func()
        func._timer.reset(now=now)
        func._is_set = True
        return func._value
    return wrapper


# decorator typing workaround
def load_credentials(ttl: int=0) -> schemas.Credentials:
    """Loads the credentials (secrets) file"""
    return _load_credentials(ttl=ttl)


@cache_func
def _load_credentials() -> schemas.Credentials:
    """Loads the credentials (secrets) file"""
    with open('credentials.yaml', 'r') as fp:
        data = yaml.safe_load(fp)
    return schemas.Credentials.from_dict(
        _apply_overrides(data, load_overrides().credentials)
    )


# decorator typing workaround
def load_config(ttl: int=0) -> schemas.Configuration:
    """Loads the playlists (configuration) file"""
    return _load_config(ttl=ttl)


@cache_func
def _load_config() -> schemas.Configuration:
    """Loads the playlists (configuration) file"""
    with open('playlists.yaml', 'r') as fp:
        data = yaml.safe_load(fp)
    return schemas.Configuration.from_dict(
        _apply_overrides(data, load_overrides().configuration)
    )


def load_overrides() -> schemas.Overrides:
    """
    Loads overrides.yaml gracefully. Relies on parent function caching.
    
    The file is intended to be a machine-writable configuration file, so
    human edits don't have to fight auto-formatting.
    """
    try:
        with open('overrides.yaml', 'r') as fp:
            return schemas.Overrides.from_dict(yaml.safe_load(fp))
    except OSError:
        return schemas.Overrides()


def _apply_overrides(data_file: Dict, overrides: Dict[str, Any]) -> Dict:
    """Loads overrides.yaml gracefully. Relies on parent function caching."""
    for override, value in overrides.items():
        jsonpath_ng.parse(override).update(data_file, value)
    return data_file


def save_overrides(overrides: schemas.Overrides):
    """Saves the overrides object."""
    with open('overrides.yaml', 'w') as fp:
        fp.write(yaml.dump(overrides.as_dict(), indent=2, sort_keys=True))


def ensure_str(text: Union[str,bytes], encoding='utf-8'):
    """An equivalent to six.ensure_str."""
    if type(text) is bytes:
        return cast(bytes, text).decode(encoding)
    return text
