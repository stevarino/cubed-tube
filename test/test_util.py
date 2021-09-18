from datetime import datetime, timedelta
import unittest

from cubed_tube.lib import util

class Data():
    def __init__(self) -> None:
        self.value = 0

class TestUtil(unittest.TestCase):
    def test_cache_func_linear(self):
        """Straight line, slope=1, should only save the start and end."""
        i = 0
        @util.cache_func
        def func():
            return i

        dt = datetime.now()
        for j in range(100):
            self.assertEqual(func(ttl=3, now=dt), j // 3 * 3)
            i += 1
            dt += timedelta(seconds=1)

    def test_cache_func_test_data(self):
        """Ensure that we can test cached functions."""
        @util.cache_func
        def func():
            raise ValueError('foo')

        self.assertRaises(ValueError, func)
        self.assertRaises(ValueError, func)

        self.assertTrue(func(_test_value=True))
        self.assertTrue(func())

    def test_cache_func_invalidate(self):
        """Ensure explicit cache invalidation is possible."""
        data = Data()
        data.value = 0

        @util.cache_func
        def func():
            data.value += 1
            return data.value

        self.assertEqual(1, func())
        self.assertEqual(1, func())
        self.assertEqual(2, func(ttl=-1))
        self.assertEqual(2, func())
        self.assertEqual(3, func(ttl=-1))


if __name__ == '__main__':
    unittest.main()