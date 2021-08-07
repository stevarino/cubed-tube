
from copy import deepcopy
from  string import ascii_lowercase
import typing
import unittest

from prometheus_client.registry import REGISTRY

from cubed_tube.backend import user_state

class MemcacheMock():
    def __init__(self, state: typing.Optional[dict]=None):
        if state is None:
            state = {}
        self.state = state

    def get(self, key):
        return self.state.get(key)

    def set(self, key, value):
        self.state[key] = value

    def gets(self, key):
        return self.get(key), 'foo'

    def cas(self, key, value, cas):
        assert cas == 'foo'
        self.set(key, value)
        return True


def _cache_init(data: typing.Optional[dict]=None, memcache=None):
    if data is None:
        data = {}

    def _miss(key):
        if key not in data:
            raise user_state.UserNotFound()
        return data[key]

    def _set(key, value):
        data[key] = value

    return user_state.Cache.cache(
        force=True,
        cache_miss=_miss,
        cache_write=_set,
        memcache=memcache
    )


class TestWsgiUser(unittest.TestCase):
    def tearDown(self) -> None:
        collectors = list(REGISTRY._collector_to_names.keys())
        [REGISTRY.unregister(c) for c in collectors]
        return super().tearDown()

    def test_cloud_storage(self):
        """Ensure that repeatedly calling the cache functions."""
        cache = _cache_init({str(i): l for i, l in enumerate(ascii_lowercase)})
        keys = [cache.read('2') for i in range(5)]
        self.assertEqual('ccccc', ''.join(keys))
        self.assertEqual(5, cache.mem_misses._value._value)
        self.assertEqual(0, cache.mem_hits._value._value)

    def test_memcache_reads(self):
        """Test that memcache reads occur before cloud reads"""
        cache = _cache_init(
            {str(i): l for i, l in enumerate(ascii_lowercase)},
            MemcacheMock())
        keys = [cache.read('2') for i in range(5)]
        self.assertEqual('ccccc', ''.join(keys))
        self.assertEqual(1, cache.mem_misses._value._value)
        self.assertEqual(4, cache.mem_hits._value._value)

    def test_merge_data_new_ids(self):
        """Ensures that new profiles receive IDs"""
        cache = _cache_init()
        data = {'a': [{'profile': 'foo'}, {'profile': 'bar'}]}
        new_data, is_merged = user_state.merge_data('hash', data)
        self.assertTrue(is_merged)
        self.assertTrue(all('id' in p for p in data['a']), data)

    def test_merge_data_not_updated(self):
        data = {'a': [{'id': 'foo', 'profile': 'foo'}]}
        _cache_init({user_state._key('hash'): deepcopy(data)})
        new_data, write_needed = user_state.merge_data('hash', data)
        self.assertFalse(write_needed)
        self.assertEqual(data, new_data)

    def test_merge_data_timestamps(self):
        data = {'a': [{'id': 'foo', 'ts': 2, 'profile': 'foo'}]}
        _cache_init({user_state._key('hash'): data})

        new_data = deepcopy(data)
        new_data['a'][0]['ts'] = 1
        final_data, is_merged = user_state.merge_data('hash', new_data)
        self.assertFalse(is_merged)
        self.assertEqual(data, final_data)
        
        new_data = deepcopy(data)
        new_data['a'][0]['ts'] = 3
        final_data, is_merged = user_state.merge_data('hash', new_data)
        self.assertTrue(is_merged)
        self.assertEqual(new_data, final_data)

    def test_tombstoned_profiles(self):
        a = {'a': [{'id': 'foo', 'ts': 2, 'profile': 'hi'}]}
        b = {'a': [{'id': 'foo'}]}

        # neither is deleted
        c = deepcopy(a)
        c['a'][0]['ts'] = 3
        final_data, is_merged = user_state.merge_data(
            'hash', c, old_data=deepcopy(a), delete_horizon=0)
        self.assertEqual(c, final_data)

        # user uploads deleted profile, server has profile
        final_data, is_merged = user_state.merge_data(
            'hash', deepcopy(b), old_data=deepcopy(a), delete_horizon=0)
        self.assertEqual(b, final_data)

        # user uploads profile, server is deleted
        final_data, is_merged = user_state.merge_data(
            'hash', deepcopy(a), old_data=deepcopy(b), delete_horizon=0)
        self.assertEqual(b, final_data)

    def test_tombstone_gc(self):
        data = {'a': [{'id': 'foo', 'ts': 1}]}
        final_data, _ = user_state.merge_data(
            'hash', deepcopy(data), old_data=deepcopy(data),
            delete_horizon=0)
        self.assertEqual(data, final_data)

        
        final_data, _ = user_state.merge_data(
            'hash', deepcopy(data), old_data=deepcopy(data),
            delete_horizon=10)

        self.assertNotEqual(data, final_data)


        

if __name__ == '__main__':
    unittest.main()