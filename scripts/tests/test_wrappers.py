import subprocess
import tempfile
import unittest
from pathlib import Path


class WrapperTests(unittest.TestCase):
    def test_wrappers_work_when_internal_scripts_are_not_executable(self):
        source = Path(__file__).resolve().parents[2]
        for wrapper, internal in [('backup-prod.sh', 'backup.sh'), ('restore-prod.sh', 'restore.sh'), ('test-restore-prod.sh', 'test_restore.sh')]:
            with self.subTest(wrapper=wrapper), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'scripts/prod').mkdir(parents=True)
                (root / wrapper).write_text((source / wrapper).read_text())
                child = root / 'scripts/prod' / internal
                child.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
                child.chmod(0o600)
                result = subprocess.run(['bash', str(root / wrapper), 'argumento com espaço'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'argumento com espaço')
