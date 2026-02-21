import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class SupabaseUserStorageHookTests(unittest.TestCase):
    def test_supabase_auth_and_storage_functions_exist(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")', text)
        self.assertIn('SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")', text)
        self.assertIn("def supabase_sign_up(email, password):", text)
        self.assertIn("def supabase_sign_in(email, password):", text)
        self.assertIn("def supabase_fetch_user_bundle(user_id, access_token):", text)
        self.assertIn("def supabase_upsert_user_bundle(user_id, access_token, bundle):", text)
        self.assertIn("def use_remote_user_store(user_id=None):", text)

    def test_data_load_save_paths_use_remote_bundle_when_available(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("if user_id is None and use_remote_user_store():", text)
        self.assertIn("bundle = load_remote_bundle()", text)
        self.assertIn("if save_remote_bundle(bundle):", text)


if __name__ == "__main__":
    unittest.main()
