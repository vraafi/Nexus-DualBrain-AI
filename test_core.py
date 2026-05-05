import unittest
import os
import sqlite3
from database import init_db, save_state, load_state, DB_NAME
from api_client import GeminiClient

class TestCoreModules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure database is clean
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
        init_db()

    def test_database_state_persistence(self):
        """Test that states can be saved and retrieved accurately."""
        task_id = "test_uuid_1234"
        save_state(task_id, "RUNNING", "test_step", {"foo": "bar"})

        state = load_state(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["current_step"], "test_step")
        self.assertEqual(state["data"].get("foo"), "bar")

    def test_api_client_key_rotation(self):
        """Test that API keys rotate correctly in the Gemini client."""
        keys = ["key1", "key2", "key3"]
        client = GeminiClient(keys)

        self.assertEqual(client._get_current_key(), "key1")
        client._rotate_key()
        self.assertEqual(client._get_current_key(), "key2")
        client._rotate_key()
        self.assertEqual(client._get_current_key(), "key3")
        client._rotate_key()
        self.assertEqual(client._get_current_key(), "key1")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)

if __name__ == "__main__":
    unittest.main()
