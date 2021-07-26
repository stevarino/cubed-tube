from base64 import b85encode
import json
import logging
import os
import time
import typing
from uuid import uuid4
from peewee import Value

from pymemcache.client import base as pymemcache_client
from pymemcache.client.retrying import RetryingClient
import pymemcache.exceptions

from prometheus_client import Counter

import hermit_tube.lib.wsgi.cloud_storage as cloud_storage

# remove profile tombstones after 30d
DELETE_HORIZON = 30 * 24 * 3600
LOGGER = logging.getLogger(__name__)

class UserNotFound(Exception):
    """The user file could not be found."""

class Cache():
    """An S3 wrapper with optional memcache read cache and write buffering."""

    _instance = None

    def __init__(self,
                 miss_func: typing.Callable[[str], None],
                 write_func: typing.Callable[[str, dict], None],
                 memcache: pymemcache_client.Client,
                 deferred_writes: bool):
        self.miss_func = miss_func
        self.write_func = write_func
        self.memcache = memcache
        self.deferred_writes = deferred_writes

        self.mem_hits = Counter(
            'ht_memcache_hit', 
            'Count of hits against memcached')
        self.mem_misses = Counter(
            'ht_memcache_miss', 
            'Count of memcached misses')
        self.mem_writes = Counter(
            'ht_memcache_writes', 
            'Count of memcached writes')
        self.mem_buffer_writes = Counter(
            'ht_memcache_buffwrites',
            'Count of memcached buffered write attempts')
        self.mem_buffer_fails = Counter(
            'ht_memcache_buffwrite_colisions',
            'Count of memcached buffered write aborts')
        # NOTE: cloud_reads will be equal to memcache missses
        # self.cloud_reads = Counter(
        #     'ht_cloud_reads', 'Count of cloud reads')
        self.cloud_writes = Counter(
            'ht_cloud_writes', 'Count of cloud writes')

        if self.deferred_writes and not self.memcache:
            raise ValueError("Cannot enable deferred_writes without memcache")

    @classmethod
    def cache(cls, force=False, cache_miss=None, cache_write=None,
              memcache=None, deferred_writes=None):
        """Factory static method"""
        if force or not cls._instance:
            if not cache_miss:
                cache_miss = cls._cache_miss
            if not cache_write:
                cache_write = cls._cache_write
            if not memcache and os.getenv('memcache'):
                host, port = os.getenv('memcache').split(':')
                memcache = RetryingClient(
                    pymemcache_client.Client((host, int(port))),
                    attempts=3,
                    retry_delay=0.1,
                    retry_for=[
                        pymemcache.exceptions.MemcacheUnexpectedCloseError,
                        ConnectionAbortedError,
                    ],
                )
            if deferred_writes is None:
                deferred_writes = bool(os.getenv('deferred_writes'))
            cls._instance = cls(cache_miss, cache_write, memcache,
                                        deferred_writes)
        return cls._instance

    @classmethod
    def _cache_miss(cls, user_hash: str):
        """Looks up user from S3 service."""
        try:
            return json.loads(cloud_storage.get_object(user_hash))
        except cloud_storage.NoSuchKey:
            raise UserNotFound()

    @classmethod
    def _cache_write(cls, user_hash: str, data: dict):
        """Writes user to S3 service."""
        cloud_storage.put_object(user_hash, json.dumps(data))

    def read(self, key):
        if self.memcache:
            result = self.memcache.get(key)
            if result:
                self.mem_hits.inc()
                return json.loads(result)
        result = self.miss_func(key)
        if self.memcache:
            self.memcache.set(key, json.dumps(result))
        self.mem_misses.inc()
        return result

    def write(self, key, value):
        self.mem_writes.inc()
        if self.memcache:
            self.memcache.set(key, json.dumps(value))
        if self.deferred_writes:
            self.mem_buffer_writes.inc()
            for i in range(3):
                result = self.memcache.get('_deferred')
                if result is None:
                    LOGGER.info('adding')
                    self.memcache.add('_deferred', '')
                    result = b''
                keys = result.decode("utf-8").split()
                if key in keys:
                    return
                try:
                    self.memcache.append('_deferred', key + ' ')
                    return
                except:
                    LOGGER.warning(
                        'Failed to append to _deferred', exc_info=True)
                    pass
                self.mem_buffer_fails.inc()
        self.cloud_writes.inc()
        self.write_func(key, value)
        
def _key(user_hash: str):
    return f'user_state/{user_hash[0:2]}/{user_hash}.json'

def lookup_user(user_hash: str):
    """Returns the user from cache/file, or throws UserNotFound."""
    return Cache.cache().read(_key(user_hash))

def merge_data(user_hash: str, data: dict, old_data=None,
               delete_horizon=None):
    """
    Given a hash and uploaded state, merges with cached data. Returns a
    two-tuple of (merged_data: dict, write_needed: bool).
    """
    if delete_horizon is None:
        delete_horizon = time.time() - DELETE_HORIZON
    if old_data is None:
        try:
            old_data = lookup_user(user_hash)
        except UserNotFound:
            [_index_profiles(data[series]) for series in data]
            return data, True

    # missing series (hc7, etc)
    for key in set(old_data.keys()) - set(data.keys()):
        data[key] = old_data[key]
    
    for series in data.keys():
        profiles = _index_profiles(data[series])

        if series not in old_data:
            continue
        old_profiles = _index_profiles(old_data[series])

        # missing profiles
        for key in set(old_profiles.keys()) - set(profiles.keys()):
            profiles[key] = old_profiles[key]
            data[series].append(profiles[key][0])

        for key, prof_index in profiles.items():
            if key not in old_profiles:
                continue
            old_profile, _ = old_profiles[key]
            profile, index = prof_index
            # tombstoned profile
            if 'profile' not in profile:
                continue
            is_deleted = 'profile' not in old_profile
            is_newer = profile.get('ts', 0) < old_profile.get('ts', 0)
            if is_deleted or is_newer:
                profiles[key] = old_profile
                data[series][index] = old_profile
        
        to_remove = []
        for i, profile in enumerate(data[series]):
            if 'profile' in profile:
                continue
            if profile.get('ts', 0) < delete_horizon:
                # insert at beginning to delete backwards, preserving order
                to_remove.insert(0, i)
        for i in to_remove:
            del data[series][i]

    return data, data != old_data 

def _index_profiles(profiles: list):
    """
    Given a list of profiles, adds an `id` field (if needed) and returns a
    id to (profile, index) dictionary. The id generation is probably overly
    complicated but it was fun to write.
    """
    values = {}
    ids = set([p.get('id') for p in profiles if p.get('id')])
    for index, profile in enumerate(profiles):
        chars = 2
        while profile.get('id') is None:
            for i in range(100):
                p_id = b85encode(uuid4().bytes).decode('ascii')[0:chars]
                if p_id not in ids:
                    break
            else:
                chars += 1
            ids.add(p_id)
            profile['id'] = p_id
        values[profile['id']] = profile, index
    return values


def write_user(user_hash: str, data: dict):
    """Writes the user to file/cache."""
    data, write_needed = merge_data(user_hash, data)
    if not write_needed:
        return data
    Cache.cache().write(_key(user_hash), data)
    return data

