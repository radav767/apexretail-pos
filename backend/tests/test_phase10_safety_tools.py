"""No production file, key, account, job, service or database is modified."""
import importlib.util,importlib.machinery,json,os,stat,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

OPS=Path(__file__).resolve().parents[2]/'ops/phase10'
def load(name,file):
    loader=importlib.machinery.SourceFileLoader(name,str(OPS/file));spec=importlib.util.spec_from_loader(name,loader)
    module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
backup=load('backup_proposal','backup_proposal.py')
mfa=load('mfa_proposal','mfa_provision.py')
runner=load('owner_runner_proposal','migration_runner.py.in')

class SafetyTools(unittest.TestCase):
    def test_backup_targets_only_production_readonly_and_has_no_password(self):
        command=backup.dump_command();self.assertIn('--dbname=apexretail_pos',command)
        self.assertTrue(any('default_transaction_read_only=on' in v for v in command));self.assertIn('--format=custom',command)
        self.assertFalse(any('password' in v.lower() for v in command))
    def test_backup_requires_verified_recipient_and_private_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);home=root/'gpg';home.mkdir(mode=0o700);cfg=root/'config.json'
            cfg.write_text(json.dumps({'recipient':None,'gnupg_home':str(home)}));cfg.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError,'fingerprint'):backup.load_config(cfg)
            cfg.write_text(json.dumps({'recipient':'A'*40,'gnupg_home':str(home)}))
            self.assertEqual(backup.load_config(cfg)['recipient'],'A'*40)
            cfg.chmod(0o644)
            with self.assertRaises(RuntimeError):backup.load_config(cfg)
    def test_mfa_key_is_private_valid_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mfa.env';mfa.provision(path);mfa.check(path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            original=path.read_bytes()
            with self.assertRaises(FileExistsError):mfa.provision(path)
            self.assertEqual(path.read_bytes(),original)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):mfa.check(path)
    def test_mfa_provision_rejects_symlink_and_public_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'target';target.write_text('untouched');link=root/'link';link.symlink_to(target)
            with self.assertRaises(FileExistsError):mfa.provision(link)
            self.assertEqual(target.read_text(),'untouched');root.chmod(0o755)
            with self.assertRaises(RuntimeError):mfa.provision(root/'new')
            root.chmod(0o700)
    def test_production_and_wrong_target_rejections_happen_before_any_connection(self):
        cases=[['--database','apexretail_pos','--action','downgrade-disposable'],
               ['--database','apexretail_pos','--action','upgrade'],
               ['--database','other_database','--action','upgrade'],
               ['--database','apexretail_pos','--action','verify','--baseline-disposable','/tmp/fake.json']]
        for args in cases:
            with self.subTest(args=args),patch.object(sys,'argv',['runner',*args]),patch.object(runner,'owner_snapshot',side_effect=AssertionError('No connection permitted')):
                with self.assertRaises(RuntimeError):runner.main()
    def test_production_maintenance_clearance_is_strict_and_short_lived(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'clearance.json'
            good={'release_commit':runner.COMMIT,'database':'apexretail_pos','sales_paused':True,'offline_queues_clear':True,
                  'approved_open_shift_count':5,'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
            with patch.object(runner,'MAINTENANCE',path),patch.object(runner,'protected'),patch.object(runner.subprocess,'run',return_value=SimpleNamespace(stdout='LoadState=loaded\nActiveState=inactive\n')):
                path.write_text(json.dumps(good));self.assertEqual(runner.clearance()['approved_open_shift_count'],5)
                for change in [{'offline_queues_clear':False},{'sales_paused':'true'},{'approved_open_shift_count':True},
                               {'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()},
                               {'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}]:
                    path.write_text(json.dumps({**good,**change}))
                    with self.subTest(change=change),self.assertRaises((RuntimeError,ValueError)):runner.clearance()
                path.write_text(json.dumps(good))
                runner.subprocess.run.return_value=SimpleNamespace(stdout='LoadState=loaded\nActiveState=active\n')
                with self.assertRaisesRegex(RuntimeError,'stopped'):runner.clearance()
    def test_backup_retention_never_deletes_existing_history(self):
        source=(OPS/'backup_proposal.py').read_text()
        self.assertNotIn('rmtree',source);self.assertNotIn('.unlink(',source);self.assertNotIn('rm -',source)
        self.assertNotIn('--trust-model',backup.encrypt_command('/private','A'*40,'/private/archive'))

if __name__=='__main__':unittest.main()
