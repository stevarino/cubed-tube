
import logging
from typing import Optional, Any, List, cast

from pymemcache.client.base import Client
from pymemcache.client.retrying import RetryingClient
import pymemcache.exceptions

from cubed_tube.lib import schema, util

CLIENT: Optional[Client] = None
LOGGER = logging.getLogger(__name__)
_DEFERRED = (util.load_credentials().site_name or '') + '/_deferred'
_ACTIONS = (util.load_credentials().site_name or '') + '/_actions'

def create_client(mc_config: schema.CredMemcache) -> Client:
    """Return a retrying memcached client"""
    global CLIENT
    if not mc_config:
        raise ValueError(
            'backend.memcache not set, is required for this feature')
    host, port = mc_config.host.split(':')
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


def add_action(action: str):
    assert '\n' not in action
    return CLIENT.append(_ACTIONS, action + '\n')


def get_action():
    result, cas = CLIENT.gets(_DEFERRED)
    if cas is None:
        CLIENT.add(_ACTIONS, '')
        return None
    if result is not None and result:
        action, rest = cast(bytes, result).decode('utf-8').strip().split('\n', 1)
        if not CLIENT.cas(_ACTIONS, rest, cas):
            return None
        return action
    return None


def get_deferred() -> tuple[List[str], int]:
    result, cas = CLIENT.gets(_DEFERRED)
    if result is not None:
        if result:
            return result.decode('utf-8').strip().split('\n'), cas
        return [], cas
    CLIENT.add(_DEFERRED, '')
    result = b''
    return get_deferred()


def set_deferred(value, cas: Any) -> bool:
    return CLIENT.cas(_DEFERRED, value, cas)


def append_deferred(value) -> bool:
    try:
        CLIENT.append(_DEFERRED, value + '\n')
        return True
    except:
        LOGGER.warning(
            'Failed to append to _deferred', exc_info=True)
    return False
