"""Regression tests for the logical digest in the #131 replay supplement."""

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_fallback_integrity import logical_digest  # noqa: E402


class LogicalDigestTests(unittest.TestCase):
    def test_order_independence_and_data_sensitivity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("one.db", "two.db")]
            values = [None, b"4142", "4142", 12, 12.5, 12]
            for path, rows in zip(paths, (values, reversed(values)), strict=True):
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute("CREATE TABLE sample(value)")
                    db.executemany("INSERT INTO sample VALUES (?)", ((v,) for v in rows))
            initial = logical_digest(paths[0])
            self.assertEqual(initial, logical_digest(paths[1]))
            with closing(sqlite3.connect(paths[1])) as db, db:
                db.execute("DELETE FROM sample WHERE rowid=1")
            self.assertNotEqual(initial, logical_digest(paths[1]))
            with closing(sqlite3.connect(paths[0])) as db, db:
                db.execute("CREATE INDEX sample_value ON sample(value)")
            self.assertNotEqual(initial, logical_digest(paths[0]))
