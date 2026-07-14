import unittest
import os
import sqlite3
import pandas as pd
import sys

# Adjust paths to import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import database as db

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Use in-memory / temporary database for testing
        self.db_file = "test_cache.db"
        db.DB_FILE = self.db_file
        db.init_db()

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_init_db(self):
        # Test that tables are created successfully
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cached_series'")
        table_exists = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(table_exists)
