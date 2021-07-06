
from copy import deepcopy
from  string import ascii_lowercase
import unittest

from hermit_tube.lib.wsgi import user_state

class TestWsgiUser(unittest.TestCase):
    _records = []

    def _lookup_user(self, hash):
        if self._records:
            return self._records.pop(0)
        raise user_state.UserNotFound()

    def _cache_init(self, data=None, **kwargs):
        cache_kwargs = {'force': True}
        for key in kwargs:
            cache_kwargs[key] = kwargs[key]
        self._records[:] = data or []
        return user_state.get_user_cache(
            self._lookup_user, force=True, **kwargs)

    def test_lru_cache_caches(self):
        """Ensure that repeatedly calling the cache functions."""
        cache = self._cache_init(list(ascii_lowercase))
        keys = [cache.get('key') for i in range(5)]
        self.assertEqual('aaaaa', ''.join(keys))
        self.assertEqual(1, cache.misses)
        self.assertEqual(4, cache.hits)
        self.assertEqual(1, len(cache.cache))
            

    def test_lru_cache_resize(self):
        """Ensures the LRU cache only returns the most recent values"""
        cache = self._cache_init(list(ascii_lowercase), maxsize=5)
        for i in range(7):
            cache.get(str(i))
        keys = ''.join(cache.cache.values())
        self.assertEqual(keys, 'cdefg')

    def test_merge_data_new_ids(self):
        """Ensures that new profiles receive IDs"""
        cache = self._cache_init()
        data = {'a': [{'profile': 'foo'}, {'profile': 'bar'}]}
        new_data, is_merged = user_state.merge_data('hash', data)
        self.assertTrue(is_merged)
        self.assertTrue(all('id' in p for p in data['a']), data)

    def test_merge_data_not_updated(self):
        data = {'a': [{'id': 'foo', 'profile': 'foo'}]}
        cache = self._cache_init([data])
        new_data, is_merged = user_state.merge_data('hash', data)
        self.assertFalse(is_merged)
        self.assertEqual(data, new_data)

    def test_merge_data_timestamps(self):
        data = {'a': [{'id': 'foo', 'ts': 2, 'profile': 'foo'}]}
        self._cache_init([deepcopy(data)])

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