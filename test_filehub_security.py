import tempfile
import unittest
from pathlib import Path
from filehub_security import hash_password, verify_password, protected_path, update_paths

class SecurityTests(unittest.TestCase):
    def test_password(self):
        credential = hash_password("strong password")
        self.assertTrue(verify_password("strong password", credential))
        self.assertFalse(verify_password("wrong password", credential))
        self.assertNotIn("strong password", str(credential))

    def test_password_length(self):
        with self.assertRaises(ValueError):
            hash_password("short")

    def test_directory_inheritance(self):
        with tempfile.TemporaryDirectory() as folder:
            sub = Path(folder) / "folder"
            sub.mkdir()
            self.assertTrue(protected_path(str(sub / "file.txt"), [str(sub)]))
            self.assertFalse(protected_path(str(Path(folder) / "folder-other.txt"), [str(sub)]))

    def test_path_update(self):
        with tempfile.TemporaryDirectory() as folder:
            old = str(Path(folder) / "old")
            new = str(Path(folder) / "new")
            self.assertEqual(update_paths([old, old + "/a.txt"], old, new), [new, new + "/a.txt"])

if __name__ == "__main__":
    unittest.main()
