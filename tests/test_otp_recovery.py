from pathlib import Path
import tempfile
import unittest
from scripts.prepare_otp_recovery import context

class RecoveryTests(unittest.TestCase):
    def files(self):return {'backend/app/main.py':b"if version != '0004_packages':\n    raise ValueError()\n",'backend/app/config.py':b"enabled = os.environ.get('SAHA_BOOKING_ENABLED', '0') == '1'\n",'index.html':b'legacy landing'}
    def test_bridge_supports_both_schemas_but_never_bypasses_phone_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);context(root,'a'*40,self.files())
            self.assertIn("('0004_packages','0005_auth_sms')",(root/'overlay/backend/app/main.py').read_text())
            self.assertIn("SAHA_BOOKING_REQUIRE_OTP",(root/'overlay/backend/app/config.py').read_text())
            self.assertTrue((root/'overlay/database/migrations/versions/0005_auth_sms.py').exists())
            self.assertIn('FROM saha-release:'+('a'*40),(root/'Dockerfile').read_text())
    def test_unexpected_source_or_secret_files_are_rejected(self):
        for name in ['.env','../outside','/root/private']:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):context(Path(directory),'a'*40,{**self.files(),name:b'not a real secret'})
