"""Fail-closed owner workflow tests; no production connections."""
import copy,hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).parent))
from release_guard import check_clearance,GateError,load,protected,payload
from snapshot import compare,PreservationError

class ReleaseGuardTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,11,28,tzinfo=timezone.utc)
  self.plan={'commit':'1'*40,'database':'apex_phase11_release_fixture','manifest_sha256':'2'*64}
  self.clearance={**self.plan,'expires_at':(self.now+timedelta(minutes=10)).isoformat(),'sales_paused':True,'open_shifts':1,'queue_policy':'retain-and-replay-original-context-v1','device_queue_inventory_sha256':'3'*64,'revocations_must_survive':True,'synthetic':True}
 def test_valid_synthetic_is_not_production_authority(self):
  check_clearance(self.plan,self.clearance,False,self.now)
  with self.assertRaises(GateError):check_clearance(self.plan,self.clearance,True,self.now)
 def test_expiry_bindings_and_queue_revocation_fences(self):
  changes=[('expires_at',(self.now-timedelta(seconds=1)).isoformat()),('expires_at',(self.now+timedelta(minutes=16)).isoformat()),('commit','9'*40),('manifest_sha256','8'*64),('sales_paused',False),('open_shifts',True),('open_shifts',-1),('queue_policy','clear-storage'),('device_queue_inventory_sha256',''),('revocations_must_survive',False)]
  for field,value in changes:
   with self.subTest(field=field,value=value),self.assertRaises(GateError):check_clearance(self.plan,{**self.clearance,field:value},False,self.now)
 def test_private_hash_and_symlink_checks(self):
  with tempfile.TemporaryDirectory(prefix='phase11-guard-negative-') as name:
   p=Path(name)/'proof.json';p.write_text('{}');p.chmod(0o600)
   self.assertEqual(load(p,hashlib.sha256(p.read_bytes()).hexdigest()),{})
   with self.assertRaises(GateError):load(p,'0'*64)
   link=Path(name)/'linked';link.symlink_to(p)
   with self.assertRaises(GateError):load(link)
   p.chmod(0o644)
   with self.assertRaises(GateError):load(p)
 def test_hidden_nested_manifest_and_linked_directory_are_rejected(self):
  import release_guard
  with tempfile.TemporaryDirectory(prefix='phase11-payload-negative-') as name:
   root=Path(name);binary=root/'python';binary.write_text('synthetic executable')
   manifest=root/'PAYLOAD.sha256';manifest.write_text(hashlib.sha256(binary.read_bytes()).hexdigest()+'  python\n')
   plan={'payload':name,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
   for key,path in [('runner',Path(release_guard.__file__)),('snapshot',Path(release_guard.__file__).with_name('snapshot.py')),('python',binary)]:plan[key]=str(path);plan[key+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
   self.assertEqual(payload(plan),root)
   (root/'nested').mkdir();extra=root/'nested/PAYLOAD.sha256';extra.write_text('unlisted')
   with self.assertRaises(GateError):payload(plan)
   extra.unlink();link=root/'linked-dir';link.symlink_to(root/'nested',target_is_directory=True)
   with self.assertRaises(GateError):payload(plan)
 def test_snapshot_rejects_data_revocation_queue_or_guard_loss(self):
  original={'tables':{'sales':'sale-hash','sessions':'revocation-hash','queue':'original-queue'},'numeric_controls':{'stock':98},'ownership':{},'open_shifts':1,'shift_enforcement':0,'app_role':{'connect':False,'schema_create':False},'triggers':[['table','immutable','guard']],'functions':{'immutable()':'original-body-hash'}}
  compare(original,copy.deepcopy(original))
  for field in original:
   changed=copy.deepcopy(original);changed[field]=[] if field=='triggers' else {} if field=='functions' else 'changed'
   with self.subTest(field=field),self.assertRaises(PreservationError):compare(original,changed)
if __name__=='__main__':unittest.main()
