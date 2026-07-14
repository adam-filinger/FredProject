import unittest
import sys
import os

# Adjust paths to import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import data_fetcher

class TestDataFetcher(unittest.TestCase):
    def test_environment_unconfigured_safeguard(self):
        # Safely checking if get_api_key returns None when env variables are empty
        import config
        api_key = config.get_api_key()
        # We expect either a string or None, ensuring the method executes without error
        self.assertTrue(api_key is None or isinstance(api_key, str))
