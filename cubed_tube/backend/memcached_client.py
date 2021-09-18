
import json
import logging
from typing import Optional, Any, List, cast, Tuple, Union

from pymemcache.client.base import Client
from pymemcache.client.retrying import RetryingClient
import pymemcache.exceptions

from cubed_tube.lib import util, schema_lib, schemas


CLIENT: Optional[Client] = None
LOGGER = logging.getLogger(__name__)


class MemcacheQueue:
    """A queue system based on memcached."""
    def __init__(self, name: str=None, full_name: str=None,
                 ttl: Optional[int]=None, touch=True):
        if name is not None:
            self.name = self.queue_name(name)
        elif full_name is not None:
            self.name = full_name
        else:
            raise ValueError('name is required')
        self.kwargs = {}
        if ttl is not None:
            self.kwargs['expire'] = ttl
        if touch:
            create_client().add(self.name, '', **self.kwargs)

    @classmethod
    def queue_name(cls, basename):
        """Returns an absolute name for a given queue basename"""
        site_name = util.load_credentials().site_name or ''
        return f'{site_name}/{basename}'

    @classmethod
    def _to_str(cls, contents: bytes) -> str:
        return contents.decode('utf-8')

    @classmethod
    def _to_list(cls, contents: bytes) -> List[str]:
        str_contents = cls._to_str(contents).strip()
        if not str_contents:
            return []
        return str_contents.split('\n')

    def push(self, record: Union[str, schema_lib.Schema]):
        """Adds an item to the end of the queue."""
        if isinstance(record, schema_lib.Schema):
            record = json.dumps(record.as_dict())
        assert '\n' not in record
        CLIENT.append(self.name, record + '\n', **self.kwargs)

    def pop(self) -> Optional[str]:
        """Attempts to return the first item on the queue, pessimistically."""
        result, cas = CLIENT.gets(self.name)
        if cas is None:
            CLIENT.cas(self.name, '', cas, **self.kwargs)
            return None
        if result is not None and result:
            action, rest = self._to_str(result).split('\n', 1)
            if not CLIENT.cas(self.name, rest, cas, **self.kwargs):
                return None
            return action
        return None

    def get_cas(self) -> Tuple[List[str], Any]:
        """Returns the full queue contents as a list of strings"""
        contents, cas = cast(bytes, CLIENT.gets(self.name, b''))
        if not contents:
            return [], cas
        return self._to_list(contents), cas

    def get(self) -> List[str]:
        """Returns the full queue contents as a list of strings"""
        return self.get_cas()[0]

    def set_cas(self, values: List[str], cas: Any):
        values.append('')  # trailing newline
        return CLIENT.cas(self.name, '\n'.join(values), cas, **self.kwargs)

    def clear(self) -> List[str]:
        """Attempts to read and wipe the queue, pessimistically."""
        result, cas = CLIENT.gets(self.name)
        if not result:
            return []
        if not CLIENT.cas(self.name, '', cas, **self.kwargs):
            return []
        return self._to_list(result)

    def is_empty(self) -> bool:
        """Reads the queue, determining if empty."""
        return not len(self)

    def __len__(self) -> int:
        """Returns the size of items stored in the queue."""
        return len(self._to_list(CLIENT.get(self.name, b'')))


def create_client() -> Client:
    """Return a retrying memcached client"""
    global CLIENT
    if CLIENT is not None:
        return CLIENT
    creds = util.load_credentials()
    if not creds.backend.memcache.host:
        raise ValueError(
            'backend.memcache not set, is required for this feature')
    host, port = creds.backend.memcache.host.split(':')
    client = RetryingClient(
        Client((host, int(port))),
        attempts=3,
        retry_delay=0.1,
        retry_for=[
            pymemcache.exceptions.MemcacheUnexpectedCloseError,
            ConnectionAbortedError,
        ],
    )
    CLIENT = client
    return client


class ActionLogger:
    """Wrapper around MemcacheQueue for ActionLog records"""
    def __init__(self, action_id: str) -> None:
        
        self.queue = MemcacheQueue(
            full_name=self.queue_name(action_id), ttl=24*3600)

    @classmethod
    def queue_name(cls, action_id):
        return MemcacheQueue.queue_name(f'_action/{action_id}')

    def log(self, **kwargs):
        self.queue.push(schemas.ActionLog.from_dict(dict(**kwargs)))

    def heading(self, content):
        self.log(heading=content)

    def html(self, content):
        self.log(html=content)

    def text(self, content):
        self.log(text=content)

    def pre_text(self, content):
        self.log(pre_text=content)

    def tombstone(self):
        self.log(tombstone=True)

DEFERRED_QUEUE = MemcacheQueue('_deferred')
ACTIONS_QUEUE = MemcacheQueue('_actions')
ACTION_LIST = MemcacheQueue('_action_list')
