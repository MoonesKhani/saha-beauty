from copy import deepcopy
import unittest
from scripts.deploy_release import ComposeEngine,DeploymentError
from scripts.deploy_otp_migration import MaintenanceEngine,ENVIRONMENT

BASE={'ADMIN_API_TOKEN':'private-admin-fixture','DATABASE_URL':'private-database-fixture','SAHA_BOOKING_ENABLED':'1'}
ACTUAL=[key+'='+value for key,value in BASE.items()]+['PATH=/bin']
DEFAULTS=['PATH=/bin']
ADDITIONS={key: '0' if value=='0' else 'private-otp-fixture' for key,value in ENVIRONMENT.items()}

class OtpEnvironmentTests(unittest.TestCase):
    def setUp(self):self.engine=MaintenanceEngine.__new__(MaintenanceEngine)
    def test_only_reviewed_additions_are_accepted_without_modifying_inputs(self):
        config={**BASE,**ADDITIONS};original=deepcopy(config)
        self.engine.verify_container_environment('app',config,ACTUAL,DEFAULTS)
        self.assertEqual(config,original)
    def test_normal_release_still_rejects_same_additions(self):
        engine=ComposeEngine.__new__(ComposeEngine)
        with self.assertRaises(DeploymentError):engine.verify_container_environment('app',{**BASE,**ADDITIONS},ACTUAL,DEFAULTS)
    def test_database_remains_strict_even_for_reviewed_key_names(self):
        with self.assertRaises(DeploymentError):self.engine.verify_container_environment('db',{**BASE,**ADDITIONS},ACTUAL,DEFAULTS)
    def test_changes_to_existing_settings_are_never_accepted_or_printed(self):
        for key in BASE:
            with self.subTest(key=key),self.assertRaises(DeploymentError) as error:
                self.engine.verify_container_environment('app',{**BASE,**ADDITIONS,key:'changed-private-fixture'},ACTUAL,DEFAULTS)
            self.assertNotIn('private-fixture',str(error.exception))
    def test_existing_otp_secret_cannot_be_changed_as_an_addition(self):
        with self.assertRaises(DeploymentError):self.engine.verify_container_environment('app',{**BASE,**ADDITIONS},ACTUAL+['SAHA_OTP_SECRET=original-private-fixture'],DEFAULTS)
    def test_unknown_new_setting_and_unrecorded_existing_setting_are_rejected(self):
        with self.assertRaises(DeploymentError):self.engine.verify_container_environment('app',{**BASE,**ADDITIONS,'CUSTOM_SETTING':'1'},ACTUAL,DEFAULTS)
        with self.assertRaises(DeploymentError):self.engine.verify_container_environment('app',{**BASE,**ADDITIONS},ACTUAL+['CUSTOM_SETTING=private-fixture'],DEFAULTS)
    def test_each_new_live_or_booking_gate_must_be_off(self):
        for key,value in ENVIRONMENT.items():
            if value=='0':
                with self.subTest(key=key),self.assertRaises(DeploymentError):self.engine.verify_container_environment('app',{**BASE,**ADDITIONS,key:'1'},ACTUAL,DEFAULTS)
