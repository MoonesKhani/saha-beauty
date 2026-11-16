from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from scripts.deploy_otp_migration import maintain,validate_recovery,ENVIRONMENT,OLD,NEW,LEGACY
from scripts.deploy_release import DeploymentError,read_state

PRIMARY={'image_id':'sha256:'+'1'*64,'commit':'a'*40,'database_revision':NEW}
RECOVERY={'image_id':'sha256:'+'2'*64,'commit':'a'*40,'database_revision':NEW,'legacy_commit':LEGACY}
ORIGINAL={'image_id':'sha256:'+'3'*64,'commit':'b'*40,'database_revision':OLD}

class Engine:
    def __init__(self):
        self.active=deepcopy(ORIGINAL);self.revision=OLD;self.calls=[];self.fail=None
        self.bookings=['before backup'];self.uploads={'owner.jpg':b'owner image'};self.settings=b'private fixture settings'
    def current(self):return deepcopy(self.active)
    def database_revision(self):return self.revision
    def check_schema(self,record):
        self.calls.append('schema')
        if record.get('database_revision')!=self.revision:raise DeploymentError('schema mismatch')
    def backup(self):
        self.calls.append('backup')
        if self.fail=='backup':raise DeploymentError('backup failure')
        return Path('/offline-fixture-backup')
    def quiet_environment(self):self.calls.append('quiet')
    def switch(self,record):self.calls.append('switch');self.active=deepcopy(record)
    def healthy(self,record):
        if self.fail=='primary' and record['image_id']==PRIMARY['image_id']:raise DeploymentError('candidate failure')
    def migrate(self,record):
        self.calls.append('migrate');self.bookings.append('after backup')
        if self.fail=='migration':raise DeploymentError('transaction rolled back')
        self.revision=NEW
    def seed(self,record):self.calls.append('seed')

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)/'state.json';self.engine=Engine()
    def test_migration_requires_compatible_recovery_metadata(self):
        manifest={**PRIMARY,'otp_recovery':RECOVERY}
        self.assertEqual(validate_recovery(manifest),RECOVERY)
        with self.assertRaises(DeploymentError):validate_recovery(PRIMARY)
        with self.assertRaises(DeploymentError):validate_recovery({**manifest,'otp_recovery':{**RECOVERY,'legacy_commit':'c'*40}})
    def test_backup_precedes_bridge_and_live_data_survives(self):
        maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertLess(self.engine.calls.index('backup'),self.engine.calls.index('quiet'))
        self.assertEqual(self.engine.revision,NEW);self.assertEqual(self.engine.active,PRIMARY)
        self.assertEqual(self.engine.bookings,['before backup','after backup'])
        self.assertEqual(read_state(self.state)['previous'],RECOVERY)
    def test_same_completed_maintenance_is_idempotent(self):
        maintain(self.engine,self.state,PRIMARY,RECOVERY)
        calls=list(self.engine.calls)
        maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertEqual(self.engine.calls,calls)
    def test_failed_backup_never_changes_image_or_database(self):
        self.engine.fail='backup'
        with self.assertRaises(DeploymentError):maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertNotIn('switch',self.engine.calls);self.assertNotIn('migrate',self.engine.calls)
    def test_failed_migration_restores_original_0004_image_only(self):
        self.engine.fail='migration'
        with self.assertRaises(DeploymentError):maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertEqual(self.engine.active,ORIGINAL);self.assertEqual(self.engine.revision,OLD)
        self.assertIn('after backup',self.engine.bookings)
    def test_failed_primary_uses_0005_recovery_and_never_restores_db(self):
        self.engine.fail='primary'
        with self.assertRaises(DeploymentError):maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertEqual(self.engine.active,RECOVERY);self.assertEqual(self.engine.revision,NEW)
        self.assertIn('after backup',self.engine.bookings)
    def test_unknown_revision_is_rejected_before_backup(self):
        self.engine.revision='unknown'
        with self.assertRaises(DeploymentError):maintain(self.engine,self.state,PRIMARY,RECOVERY)
        self.assertNotIn('backup',self.engine.calls)
    def test_all_send_and_booking_gates_are_forced_off(self):
        for key in ['SAHA_OTP_ENABLED','SAHA_SMS_LIVE_ENABLED','SAHA_SMS_NOTIFICATIONS_ENABLED','SAHA_BOOKING_REQUIRE_OTP']:
            self.assertEqual(ENVIRONMENT[key],'0')
        self.assertEqual(ENVIRONMENT['MELIPAYAMAK_API_KEY'],'${MELIPAYAMAK_API_KEY:-}')
