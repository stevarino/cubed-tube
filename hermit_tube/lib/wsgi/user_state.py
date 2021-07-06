from base64 import b85encode
from collections import OrderedDict
import json
import time
from uuid import uuid4

import hermit_tube.lib.wsgi.bucket as bucket

# remove profile tombstones after 30d
DELETE_HORIZON = 30 * 24 * 3600

class UserNotFound(Exception):
    """The user file could not be found."""

class Cache():
    """An LRU cache with the ability to update cache items."""
    def __init__(self, user_func, maxsize=1000):
        self.user_func = user_func
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        self.cache = OrderedDict()

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        result = self.user_func(key)
        self.cache[key] = result
        self.misses += 1
        self.resize()
        return result

    def update(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        self.resize()

    def resize(self):
        while len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)


_user_cache = None

def get_user_cache(lookup_user_func = None, force=False, maxsize=None):
    """Initializes, caches (yo dawg), and returns the User Cache object."""
    global _user_cache
    kwargs = {}
    if lookup_user_func is None:
        lookup_user_func = _lookup_user
    if maxsize is not None:
        kwargs['maxsize'] = maxsize
    if _user_cache is None or force:
        _user_cache = Cache(lookup_user_func, **kwargs)
    return _user_cache

def _lookup_user(user_hash: str):
    """Looks up user from the filesystem."""
    try:
        return json.loads(bucket.get_object(_key(user_hash)))
    except bucket.NoSuchKey:
        raise UserNotFound()

def _key(user_hash: str):
    return f'user_state/{user_hash[0:2]}/{user_hash}.json'

def lookup_user(user_hash: str):
    """Returns the user from cache/file, or throws UserNotFound."""
    cache = get_user_cache()
    return cache.get(user_hash)

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
    bucket.put_object(_key(user_hash), json.dumps(data))
    cache = get_user_cache()
    cache.update(user_hash, data)
    return data

