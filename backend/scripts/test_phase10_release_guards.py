"""Preparation guard tests: no database connection required or permitted."""
import unittest
from unittest.mock import patch
import prepare_phase10_release as release

class ReleaseGuards(unittest.TestCase):
    def test_live_writes_are_rejected_before_connect(self):
        with patch.object(release.psycopg2,'connect',side_effect=AssertionError('Network must not be called')):
            with self.assertRaisesRegex(RuntimeError,'read-only'):release.connect('apexretail_pos')
            with self.assertRaisesRegex(RuntimeError,'allowlisted'):release.connect('unapproved_database')
    def test_live_restore_and_migration_targets_are_rejected(self):
        with patch.object(release.psycopg2,'connect',side_effect=AssertionError('Network must not be called')):
            with self.assertRaisesRegex(RuntimeError,'restore refused'):release.create_and_restore('apexretail_pos',None)
            with self.assertRaisesRegex(RuntimeError,'migration refused'):release.assert_clone('apexretail_pos')
    def test_snapshot_comparison_rejects_changed_financial_content(self):
        before={'tables':{'sales':{'count':1,'sha256':'original'}},'numeric_control_totals':{'sales':'10.00'},'enforcement_enabled':0,'open_shifts':5,'schema_create':True,'ownership':{'sales':{'owner':'postgres'}},'columns':{'sales':['id']}}
        for key,value in [('tables',{}),('numeric_control_totals',{}),('enforcement_enabled',1),('open_shifts',0),('schema_create',False),('ownership',{'sales':{'owner':'other'}})]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):release.compare(before,{**before,key:value})
        release.compare(before,before)

if __name__=='__main__':unittest.main(verbosity=2)
