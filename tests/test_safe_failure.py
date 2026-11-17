import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.deploy_release import DeploymentError
from scripts.deploy_otp_migration import FAILURE_CONTEXT,record_failure
from scripts.deploy_receiver import transaction_info
from types import SimpleNamespace

class FailureTests(unittest.TestCase):
    def test_failure_metadata_never_contains_exception_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.dict(FAILURE_CONTEXT,{'project':root,'commit':'a'*40,'stage':'load-approved-images'},clear=True),patch.dict(os.environ,{'INVOCATION_ID':'b'*32}):
                record_failure(DeploymentError('private-credential-value',diagnostic='secret-private-value'))
            data=(root/'.deploy/last-failure.json').read_text()
            self.assertNotIn('private',data);self.assertNotIn('secret',data)
            self.assertEqual(json.loads(data)['operation'],'deployment safety check')
    def test_receiver_rejects_stale_or_other_commit_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.deploy').mkdir()
            file=root/'.deploy/last-failure.json'
            file.write_text(json.dumps({'commit':'a'*40,'invocation_id':'b'*32,'stage':'load-approved-images','operation':'verify image identity'}))
            process=SimpleNamespace(returncode=0,stdout='LoadState=loaded\nActiveState=failed\nResult=exit-code\nInvocationID='+'b'*32)
            store=SimpleNamespace(commit='a'*40,unit='fixture')
            with patch('scripts.deploy_receiver.subprocess.run',return_value=process):
                self.assertEqual(transaction_info(store,root)['failure']['operation'],'verify image identity')
                store.commit='c'*40;self.assertNotIn('failure',transaction_info(store,root))
                store.commit='a'*40;process.stdout=process.stdout.replace('b'*32,'d'*32)
                self.assertNotIn('failure',transaction_info(store,root))
