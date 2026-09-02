import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('operations', Path(__file__).resolve().parents[1] / 'prod' / 'operations.py')
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = dict(ops.CFG)
        self.addCleanup(lambda: (ops.CFG.clear(), ops.CFG.update(self.config)))
        ops.CFG.update(backup_root=str(self.root), state_dir=str(self.root / 'state'), remote='encrypted:backups')

    def backup(self, name='20260902_120000_1234abcd', member='photo.txt'):
        path = self.root / name
        path.mkdir()
        (path / 'database.dump').write_bytes(b'test dump')
        (path / 'manifest.json').write_text('{}')
        with tarfile.open(path / 'media.tar.gz', 'w:gz') as archive:
            info = tarfile.TarInfo(member)
            info.size = 4
            archive.addfile(info, io.BytesIO(b'test'))
        (path / 'SHA256SUMS').write_text(''.join(f'{ops.digest(path / f)}  {f}\n' for f in ops.FILES))
        (path / 'COMPLETE').write_text('complete\n')
        return path

    def test_corrupt_dump_is_rejected(self):
        path = self.backup()
        (path / 'database.dump').write_bytes(b'corrupted')
        with self.assertRaises(RuntimeError): ops.validate_backup(path)

    def test_safe_media_and_manifest_validate(self):
        path = self.backup()
        self.assertEqual(ops.validate_backup(path), path)

    def test_media_path_traversal_is_rejected(self):
        path = self.backup(member='../escape')
        with self.assertRaises(RuntimeError): ops.validate_backup(path)

    def test_failed_set_is_not_selected(self):
        path = self.backup()
        (path / 'FAILED').touch()
        with self.assertRaises(RuntimeError): ops.latest_backup()

    def test_external_failure_does_not_mark_verified(self):
        path = self.backup()
        with patch.object(ops, 'run', side_effect=[b'', RuntimeError('remote failure')]):
            with self.assertRaises(RuntimeError): ops.upload_backup(path)
        self.assertFalse((path / 'REMOTE_VERIFIED.json').exists())

    def test_complete_is_uploaded_only_after_verification(self):
        path = self.backup()
        with patch.object(ops, 'run', side_effect=[b'', b'', b'', b'complete\n']) as run:
            ops.upload_backup(path)
        self.assertEqual(run.call_args_list[1].args[0][1], 'check')
        self.assertEqual(run.call_args_list[2].args[0][1], 'copyto')
        self.assertTrue((path / 'REMOTE_VERIFIED.json').exists())

    def test_rollback_refuses_migration_changes_before_docker_mutation(self):
        name = '20260902_120000_1234abcd'
        ops.CFG['release_root'] = str(self.root)
        path = self.root / name
        path.mkdir()
        ops.atomic_json(path / 'release.json', {'compose_file': ops.CFG['compose_file'], 'migrations': [['app', '0001']]})
        with patch.object(ops, 'migration_snapshot', return_value=[['app', '0002']]), patch.object(ops, 'run') as run:
            with self.assertRaises(RuntimeError): ops.rollback(name, True)
        run.assert_not_called()

    def test_rollback_requires_explicit_confirmation(self):
        with patch.object(ops, 'run') as run:
            with self.assertRaises(RuntimeError): ops.rollback('20260902_120000_1234abcd', False)
        run.assert_not_called()

    def test_alert_is_sent_only_on_transition(self):
        ops.CFG['webhook_url'] = 'https://example.invalid/hook'
        with patch.object(ops.urllib.request, 'urlopen') as request:
            request.return_value.__enter__.return_value.status = 200
            ops.notify(['Service down'])
            ops.notify(['Service down'])
            ops.notify([])
        self.assertEqual(request.call_count, 2)

    def test_restore_test_cleans_temporary_database_on_failure(self):
        path = self.backup()
        with patch.object(ops, 'db_identity', return_value=('user', 'production')), patch.object(ops, 'dc') as dc, patch.object(ops.subprocess, 'run', side_effect=RuntimeError('restore failed')):
            with self.assertRaises(RuntimeError): ops.restore_test(path)
        self.assertIn('dropdb', dc.call_args.args)
        self.assertTrue(dc.call_args.args[-1].startswith('vdd_restore_test_'))
        self.assertNotEqual(dc.call_args.args[-1], 'production')

    def test_restore_requires_confirmation_before_backup_or_stop(self):
        path = self.backup()
        with patch.object(ops, 'db_identity', return_value=('user', 'production')), patch.object(ops.sys.stdin, 'isatty', return_value=False), patch.object(ops, 'backup') as backup, patch.object(ops, 'dc') as dc:
            with self.assertRaises(RuntimeError): ops.restore_production(path, False)
        backup.assert_not_called()
        dc.assert_not_called()

    def test_restore_failure_keeps_application_stopped(self):
        path = self.backup()
        with patch.object(ops, 'db_identity', return_value=('user', 'production')), patch.object(ops, 'backup') as backup, patch.object(ops, 'dc') as dc, patch.object(ops.subprocess, 'run', side_effect=RuntimeError('failure')):
            with self.assertRaisesRegex(RuntimeError, 'mantida parada'):
                ops.restore_production(path, True)
        backup.assert_called_once_with(prune=False)
        self.assertEqual(dc.call_args_list[0].args[0], 'stop')
        self.assertFalse(any(call.args[0] in ('start', 'up') for call in dc.call_args_list))



if __name__ == '__main__':
    unittest.main()
