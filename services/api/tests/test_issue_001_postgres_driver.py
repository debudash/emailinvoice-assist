"""ISSUE-001 regression test.

Found by: first `docker compose up` of the starter (2026-10-19); the API exited with
ModuleNotFoundError: No module named 'psycopg'.
"""
import unittest

from sqlalchemy import make_url


class TestIssue001PostgresDriver(unittest.TestCase):
    def test_plain_postgresql_url_uses_installed_psycopg2_driver(self):
        # The compose file passes a plain postgresql:// URL; it must resolve to psycopg2,
        # the only Postgres driver in requirements.txt.
        dialect = make_url("postgresql://ctref:ctref@db:5432/ctref").get_dialect()
        self.assertEqual(dialect.driver, "psycopg2")


if __name__ == "__main__":
    unittest.main()
