from cubed_tube.lib import trends
from cubed_tube.lib import models

import unittest

import peewee as pw

class TestTrends(unittest.TestCase):
    def run(self, result=None):
        test_db = pw.SqliteDatabase(":memory:")
        with test_db.bind_ctx(models.MODELS):
            test_db.create_tables(models.MODELS)
            super().run(result)

    def _tp(self):
        return [(p.timestamp, p.value) for p in models.TrendPoint.select()]

    def test_linear(self):
        """Straight line, slope=1, should only save the start and end."""
        ts = models.TrendSeries.create()
        for i in range(100):
            trends.add_point(ts, i, i)
        self.assertEqual(ts.raw_count, 100)
        self.assertEqual(ts.point_count, 2)
        self.assertEqual(len(models.TrendPoint.select()), 2, self._tp())

    def test_exception(self):
        """Up, over, and down. Should save the 4 corners."""
        ts = models.TrendSeries.create()
        for i in range(100):
            trends.add_point(ts, i, i)
        trends.add_point(ts, 100, 99)
        for i in range(100):
            trends.add_point(ts, i+101, 99-i)
        self.assertEqual(len(models.TrendPoint.select()), 3, self._tp())

if __name__ == '__main__':
    unittest.main()