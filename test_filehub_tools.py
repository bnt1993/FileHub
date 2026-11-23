import os
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from filehub_tools import rename_plan, apply_renames, duplicates, export_csv, export_xlsx


class ToolsTests(unittest.TestCase):
    def test_batch_rename(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / "a.txt"
            b = Path(folder) / "b.txt"
            a.write_text("a")
            b.write_text("b")
            plan = rename_plan([str(a), str(b)], prefix="new_", start=1)
            apply_renames(plan)
            self.assertTrue((Path(folder) / "new_1_a.txt").exists())
            self.assertTrue((Path(folder) / "new_2_b.txt").exists())

    def test_collision_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / "a.txt"
            b = Path(folder) / "new_a.txt"
            a.write_text("a")
            b.write_text("b")
            with self.assertRaises(FileExistsError):
                rename_plan([str(a)], prefix="new_")

    def test_duplicates_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, value in (("a.txt", "same"), ("b.txt", "same"), ("c.txt", "different")):
                (Path(folder) / name).write_text(value)
            groups, count, capped = duplicates(folder)
            self.assertEqual(count, 3)
            self.assertFalse(capped)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]), 2)
            self.assertEqual(len(list(Path(folder).iterdir())), 3)

    def test_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [("báo cáo.xlsx", "Excel", 123, "23/11/2026", r"C:\\báo cáo.xlsx")]
            csv_path = str(Path(folder) / "report.csv")
            xlsx_path = str(Path(folder) / "report.xlsx")
            export_csv(csv_path, rows)
            export_xlsx(xlsx_path, rows)
            self.assertIn("báo cáo", Path(csv_path).read_text(encoding="utf-8-sig"))
            with ZipFile(xlsx_path) as archive:
                xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                self.assertIn("báo cáo", xml)
                self.assertIn("<v>123</v>", xml)


if __name__ == "__main__":
    unittest.main()
