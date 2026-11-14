"""Release approval, archive integrity and rollback preserve live data."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from scripts.deploy_release import DeploymentError,apply_release,atomic_json,deployment_lock,unpack_bundle,verify_environment
from scripts.deploy_receiver import parse_command,receive
from scripts.validate_release_run import validate

SHA='a'*40
OLD={'image_id':'sha256:'+'1'*64,'commit':'b'*40,'database_revision':'0004_packages'}
NEW={'image_id':'sha256:'+'2'*64,'commit':SHA,'database_revision':'0004_packages'}

class FixtureEngine:
    def __init__(self,root):
        self.root=root;self.active=deepcopy(OLD);self.calls=[];self.fail_health=False;self.fail_backup=False
        self.bookings=['original booking'];self.uploads={'photo.webp':b'owner photo'}
        (root/'.env').write_text('PRIVATE_FIXTURE=preserve\n')
    def current(self):return deepcopy(self.active)
    def check_schema(self,record):
        self.calls.append('schema')
        if record.get('database_revision')!='0004_packages':raise DeploymentError('migration requires separate approval')
    def backup(self):
        self.calls.append('backup')
        if self.fail_backup:raise DeploymentError('backup failed')
        folder=self.root/'backup';folder.mkdir(exist_ok=True);return folder
    def seed(self,record):self.calls.append('seed')
    def switch(self,record):
        self.calls.append('switch');self.active=deepcopy(record)
        if self.fail_health and record['image_id']==NEW['image_id']:self.bookings.append('booking accepted after backup')
    def healthy(self,record):
        if self.fail_health and record['image_id']==NEW['image_id']:raise DeploymentError('bad application')

class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'state.json';self.engine=FixtureEngine(self.root)
    def assert_data(self):
        self.assertEqual((self.root/'.env').read_text(),'PRIVATE_FIXTURE=preserve\n')
        self.assertEqual(self.engine.uploads,{'photo.webp':b'owner photo'})
        self.assertIn('original booking',self.engine.bookings)
    def test_healthy_switch_and_manual_rollback_keep_new_bookings(self):
        state=apply_release(self.engine,self.path,deepcopy(NEW))
        self.assertEqual(state['previous'],OLD);self.assertEqual(self.engine.active,NEW)
        self.engine.bookings.append('booking after successful release')
        result=apply_release(self.engine,self.path,deepcopy(OLD),rollback=True)
        self.assertEqual(result['current'],OLD)
        self.assertIn('booking after successful release',self.engine.bookings);self.assert_data()
    def test_failed_health_restores_only_image_not_live_data(self):
        self.engine.fail_health=True
        with self.assertRaises(DeploymentError):apply_release(self.engine,self.path,deepcopy(NEW))
        self.assertEqual(self.engine.active,OLD)
        self.assertIn('booking accepted after backup',self.engine.bookings)
        self.assertEqual(json.loads(self.path.read_text())['phase'],'rolled_back');self.assert_data()
    def test_new_database_revision_is_blocked_before_mutation(self):
        candidate={**NEW,'database_revision':'0005_breaking'}
        with self.assertRaises(DeploymentError):apply_release(self.engine,self.path,candidate)
        self.assertNotIn('backup',self.engine.calls);self.assertNotIn('seed',self.engine.calls);self.assertNotIn('switch',self.engine.calls)
        self.assertFalse(self.path.exists());self.assert_data()
    def test_backup_failure_keeps_existing_service_running(self):
        self.engine.fail_backup=True
        with self.assertRaises(DeploymentError):apply_release(self.engine,self.path,deepcopy(NEW))
        self.assertNotIn('switch',self.engine.calls);self.assertEqual(self.engine.active,OLD);self.assert_data()
    def test_stale_rollback_approval_is_rejected(self):
        apply_release(self.engine,self.path,deepcopy(NEW));before=list(self.engine.calls)
        with self.assertRaises(DeploymentError):apply_release(self.engine,self.path,{'image_id':'sha256:'+'3'*64},rollback=True)
        self.assertEqual(self.engine.calls,before);self.assertEqual(self.engine.active,NEW);self.assert_data()
    def test_interrupted_deploy_requires_explicit_recovery(self):
        atomic_json(self.path,{'phase':'switching','current':OLD,'candidate':NEW})
        with self.assertRaises(DeploymentError):apply_release(self.engine,self.path,deepcopy(NEW))
        self.assertEqual(self.engine.calls,[]);self.assert_data()
    def test_failed_image_rollback_records_recoverable_state(self):
        def fail(record):raise DeploymentError('all health probes fail')
        self.engine.healthy=fail
        with self.assertRaisesRegex(DeploymentError,'rollback failed'):apply_release(self.engine,self.path,deepcopy(NEW))
        self.assertEqual(json.loads(self.path.read_text())['phase'],'rollback_failed');self.assert_data()
    def test_server_lock_rejects_simultaneous_deployments(self):
        with deployment_lock(self.root):
            with self.assertRaises(DeploymentError):
                with deployment_lock(self.root):pass
        with deployment_lock(self.root):pass

class BundleTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def bundle(self,changes=None,extra=None):
        data=b'image archive fixture'
        manifest={'format':1,'commit':SHA,'image_tag':'saha-release:'+SHA,'image_id':NEW['image_id'],'database_revision':'0004_packages','image_sha256':hashlib.sha256(data).hexdigest(),'image_bytes':len(data)}
        manifest.update(changes or {})
        bundle=self.root/'release.tar'
        with tarfile.open(bundle,'w') as archive:
            for name,body in [('manifest.json',json.dumps(manifest).encode()),('image.tar.gz',data)]:
                item=tarfile.TarInfo(name);item.size=len(body);archive.addfile(item,BytesIO(body))
            if extra:archive.addfile(extra)
        return bundle
    def test_exact_approved_bundle(self):
        manifest,image=unpack_bundle(self.bundle(),self.root/'stage',SHA)
        self.assertEqual(manifest['image_id'],NEW['image_id']);self.assertEqual(image.read_bytes(),b'image archive fixture')
    def test_corruption_is_rejected(self):
        with self.assertRaisesRegex(DeploymentError,'checksum'):unpack_bundle(self.bundle({'image_sha256':'0'*64}),self.root/'stage',SHA)
    def test_different_commit_is_rejected(self):
        with self.assertRaises(DeploymentError):unpack_bundle(self.bundle({'commit':'b'*40}),self.root/'stage',SHA)
    def test_traversal_and_symlinks_are_rejected(self):
        for index,name in enumerate(['../outside','/etc/override','image-link']):
            item=tarfile.TarInfo(name)
            if name=='image-link':item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd'
            with self.assertRaises(DeploymentError):unpack_bundle(self.bundle(extra=item),self.root/f'stage{index}',SHA)
            self.assertFalse((self.root/'outside').exists())
    def test_receive_size_limit(self):
        with self.assertRaises(ValueError):receive(BytesIO(b'a'*100),self.root/'incoming',limit=50)

class ApprovalTest(unittest.TestCase):
    def valid_run(self):return {'repository':{'full_name':'MoonesKhani/saha-beauty'},'head_repository':{'full_name':'MoonesKhani/saha-beauty'},'head_sha':SHA,'head_branch':'main','event':'push','status':'completed','conclusion':'success','path':'.github/workflows/ci.yml'}
    def test_successful_main_run_is_eligible_but_still_needs_confirmation(self):
        validate(self.valid_run(),'MoonesKhani/saha-beauty',SHA,'DEPLOY '+SHA)
        with self.assertRaises(ValueError):validate(self.valid_run(),'MoonesKhani/saha-beauty',SHA,'')
    def test_pr_failed_wrong_sha_and_fork_runs_cannot_deploy(self):
        for change in [{'event':'pull_request'},{'head_branch':'feature'},{'conclusion':'failure'},{'head_sha':'b'*40},{'head_repository':{'full_name':'someone/fork'}},{'path':'.github/workflows/other.yml'}]:
            with self.assertRaises(ValueError):validate({**self.valid_run(),**change},'MoonesKhani/saha-beauty',SHA,'DEPLOY '+SHA)
    def test_ssh_receiver_accepts_only_fixed_operations(self):
        self.assertEqual(parse_command('deploy '+SHA),('deploy',SHA))
        self.assertEqual(parse_command('rollback '+OLD['image_id']),('rollback',OLD['image_id']))
        self.assertEqual(parse_command('status'),('status',None))
        self.assertEqual(parse_command('site '+OLD['image_id']),('site',OLD['image_id']))
        for command in ['bash','deploy '+SHA+'; id','deploy '+SHA+'\n','rollback /tmp/file','scp -t /root/.ssh/authorized_keys']:
            with self.assertRaises(ValueError):parse_command(command)


class ConfigurationTest(unittest.TestCase):
    def test_existing_compose_settings_are_preserved(self):
        verify_environment({'ADMIN_API_TOKEN':'fixture'},['PATH=/bin','ADMIN_API_TOKEN=fixture'],['PATH=/bin'])
    def test_pending_env_change_stops_instead_of_overwriting(self):
        with self.assertRaises(DeploymentError) as error:
            verify_environment({'ADMIN_API_TOKEN':'new-private-fixture'},['ADMIN_API_TOKEN=old-private-fixture'],[])
        self.assertNotIn('private-fixture',str(error.exception))
    def test_unrecorded_runtime_setting_is_not_silently_lost(self):
        with self.assertRaises(DeploymentError):verify_environment({},['CUSTOM_SETTING=preserve'],[])

if __name__=='__main__':unittest.main()
