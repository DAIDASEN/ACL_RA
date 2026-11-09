import csv
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from manage import validate_passages


class ManagementTests(unittest.TestCase):
    def write_csv(self, directory, rows, fields=None):
        path = Path(directory) / 'passages.csv'
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields or ['passage_id', 'passage'])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_valid_input_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [dict(passage_id='P001', passage=' '.join(['word'] * 150)),
                    dict(passage_id='P002', passage=' '.join(['other'] * 300))]
            path = self.write_csv(directory, rows)
            self.assertEqual(len(validate_passages(path, 2)), 2)
            with self.assertRaises(ValueError):
                validate_passages(path, 120)
            rows[1]['passage_id'] = 'P001'
            with self.assertRaises(ValueError):
                validate_passages(self.write_csv(directory, rows), 2)
            rows[1]['passage_id'] = 'P002'
            rows[1]['passage'] = rows[0]['passage']
            with self.assertRaises(ValueError):
                validate_passages(self.write_csv(directory, rows), 2)
            rows[1]['passage'] = 'short text'
            with self.assertRaises(ValueError):
                validate_passages(self.write_csv(directory, rows), 2)

    def test_teacher_scripts_unchanged(self):
        source = ROOT / 'docs/source/实验2 脚本.zip'
        if not source.exists():
            self.skipTest('requires the private original ZIP')
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                self.assertEqual(archive.read(name), (ROOT / 'src/teacher' / name).read_bytes())

    def test_all_original_sources_match_manifest(self):
        workspace = ROOT.parent
        manifest = workspace / 'internal/source/SOURCE_MANIFEST.json'
        if not manifest.exists():
            self.skipTest('requires the private source manifest')
        records = json.loads(manifest.read_text())
        for record in records:
            content = (workspace / record['current_path']).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), record['sha256'])


if __name__ == '__main__':
    unittest.main()
