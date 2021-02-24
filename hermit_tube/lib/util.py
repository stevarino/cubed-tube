import hashlib
import os.path
from typing import Union
import yaml

class Struct(object):
    def __init__(self, data):
        for name, value in data.items():
            setattr(self, name, self._wrap(value))

    def _wrap(self, value):
        if isinstance(value, (tuple, list, set, frozenset)): 
            return type(value)([self._wrap(v) for v in value])
        else:
            return Struct(value) if isinstance(value, dict) else value

_cache = {}

def root(*paths):
    path = os.path.abspath(__file__).replace('\\', '/')
    while 'hermit_tube/lib' in path:
        path = os.path.dirname(path).replace('\\', '/')
    return os.path.join(path, *paths)

def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()

def credentials():
    if 'credentials.yaml' not in _cache:
        with open(root('credentials.yaml')) as fp:
            _cache['credentials.yaml'] = Struct(yaml.safe_load(fp))
    return _cache['credentials.yaml']
