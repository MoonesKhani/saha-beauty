import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts.arvan_transfer import configuration,DownloadError

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'endpoint':'https://s3.ir-fixture.arvanstorage.ir','bucket':'private-fixture','region':'ir-fixture','prefix':'saha-releases/'}
class ConfigurationTests(unittest.TestCase):
    def test_blank_workflow_variables_use_nonsecret_checked_in_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'policy.json';path.write_text(json.dumps(CONFIG))
            with patch('scripts.arvan_transfer.CONFIG_FILE',path),patch.dict(os.environ,{'ARVAN_STORAGE_'+k.upper():'' for k in CONFIG}):
                self.assertEqual(configuration(),CONFIG)
    def test_explicit_variables_remain_supported(self):
        with patch.dict(os.environ,{'ARVAN_STORAGE_'+k.upper():v for k,v in CONFIG.items()}):self.assertEqual(configuration(),CONFIG)
    def test_malformed_config_stops_before_network_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'policy.json';path.write_text('not JSON')
            with patch('scripts.arvan_transfer.CONFIG_FILE',path),self.assertRaises(DownloadError):configuration()
    def test_missing_storage_secrets_report_names_without_values_or_ssh(self):
        env={**os.environ,'OPERATION':'artifact-probe','RELEASE_TRANSPORT':'arvan','ARVAN_SSH_KEY':'fixture-private-do-not-print','ARVAN_KNOWN_HOSTS':'fixture-host-do-not-print'}
        for name in ['ARVAN_STORAGE_ACCESS_KEY_ID','ARVAN_STORAGE_SECRET_ACCESS_KEY']:env.pop(name,None)
        result=subprocess.run(['bash',str(ROOT/'scripts/approved_transport.sh')],env=env,capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,1)
        for name in ['ARVAN_STORAGE_ACCESS_KEY_ID','ARVAN_STORAGE_SECRET_ACCESS_KEY']:self.assertIn(name,result.stdout)
        self.assertNotIn('fixture-private',result.stdout+result.stderr);self.assertNotIn('fixture-host',result.stdout+result.stderr)
