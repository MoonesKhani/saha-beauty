import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import zipfile
from scripts.artifact_fetch import storage_policy,storage_policy_hash,valid_url,fetch,ArtifactError
from scripts.arvan_transfer import stage,prepare_zip,publish,client
from scripts.https_release import DownloadError

POLICY={'endpoint':'https://s3.ir-fixture.arvanstorage.ir','bucket':'saha-private-fixture','region':'ir-fixture','prefix':'saha-releases/'}
COMMIT='a'*40
class Sender:
    commit=COMMIT
    def __init__(self,root):
        self.bundle=root/'release.tar';self.bundle.write_bytes(b'offline fixture, not an installable image')
        self.size=self.bundle.stat().st_size;self.digest=hashlib.sha256(self.bundle.read_bytes()).hexdigest();self.calls=[]
    def request(self,command,data=None,timeout=None):
        self.calls.append((command,data))
        return {'arvan_fetch':True,'arvan_policy_hash':storage_policy_hash(POLICY)} if command=='status' else {'complete':True,'bytes':self.size}

class ArvanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.sender=Sender(self.root)
    def location(self):return POLICY['endpoint']+'/'+POLICY['bucket']+'/'+POLICY['prefix']+COMMIT+'/'+'b'*64+'.zip?X-Amz-Signature=offline-fixture'
    def test_sdk_is_explicitly_configured_without_network_or_instance_credentials(self):
        with patch.dict(os.environ,{'ARVAN_STORAGE_ACCESS_KEY_ID':'offline-fixture','ARVAN_STORAGE_SECRET_ACCESS_KEY':'offline-fixture'}),patch('boto3.client') as factory:
            client(POLICY)
        options=factory.call_args.kwargs;config=options['config']
        self.assertEqual(options['endpoint_url'],POLICY['endpoint'])
        self.assertEqual(options['aws_access_key_id'],'offline-fixture')
        self.assertEqual(options['aws_secret_access_key'],'offline-fixture')
        self.assertEqual(config.signature_version,'s3v4')
        self.assertEqual(config.s3['addressing_style'],'path')
        self.assertEqual(config.request_checksum_calculation,'when_required')
    def test_destination_is_exact_and_confined(self):
        location=self.location();self.assertEqual(valid_url(location,policy=POLICY),location)
        for changed in ['https://productionresultssa7.blob.core.windows.net/actions-results/fixture',location.replace('saha-private-fixture','other-bucket'),location.replace('/saha-releases/','/user-uploads/'),location.replace('/saha-releases/','/saha-releases/../'),location.replace('/saha-releases/','/saha-releases/%2e%2e/'),location.replace('ir-fixture.arvanstorage.ir','ir-other.arvanstorage.ir'),location.replace('https:','http:'),location.replace('https://','https://user:private@')]:
            with self.assertRaises(ValueError):valid_url(changed,policy=POLICY)
        for endpoint in ['https://127.0.0.1','http://s3.ir-fixture.arvanstorage.ir','https://s3.ir-fixture.arvanstorage.ir.evil.invalid','https://s3.ir-fixture.arvanstorage.ir/private']:
            with self.assertRaises(ValueError):storage_policy({**POLICY,'endpoint':endpoint})
    def test_unconfigured_receiver_rejects_before_any_upload(self):
        self.sender.request=lambda *args,**kwargs:{'arvan_fetch':False}
        with patch('scripts.arvan_transfer.configuration',return_value=POLICY),patch('scripts.arvan_transfer.client') as client:
            with self.assertRaises(DownloadError):stage(self.sender)
            client.assert_not_called()
    def test_policy_mismatch_rejects_before_any_upload(self):
        self.sender.request=lambda *args,**kwargs:{'arvan_fetch':True,'arvan_policy_hash':'wrong'}
        with patch('scripts.arvan_transfer.configuration',return_value=POLICY),patch('scripts.arvan_transfer.client') as client:
            with self.assertRaises(DownloadError):stage(self.sender)
            client.assert_not_called()
    def test_zip_is_deterministic_and_compatible_with_verified_receiver(self):
        path,digest=prepare_zip(self.sender);first=path.read_bytes()
        self.assertEqual(prepare_zip(self.sender)[1],digest);self.assertEqual(path.read_bytes(),first)
        class Response(BytesIO):
            read1=BytesIO.read
            def __init__(self):super().__init__(first);self.status=206;self.headers={'Content-Range':f'bytes 0-{len(first)-1}/{len(first)}'}
        with patch('scripts.artifact_fetch.installed_storage_policy',return_value=POLICY):
            result=fetch(self.location(),self.root/'received.tar',self.sender.digest,self.sender.size,digest,len(first),open_url=lambda *args,**kwargs:Response())
        self.assertTrue(result['complete']);self.assertEqual((self.root/'received.tar').read_bytes(),self.sender.bundle.read_bytes())
    def test_upload_failure_never_requests_download_or_installation(self):
        with patch('scripts.arvan_transfer.configuration',return_value=POLICY),patch('scripts.arvan_transfer.client'),patch('scripts.arvan_transfer.publish',side_effect=DownloadError('upload failed')):
            with self.assertRaises(DownloadError):stage(self.sender)
        self.assertEqual(self.sender.calls,[('status',None)])
    def test_signed_link_only_in_encrypted_stdin_and_never_deploys(self):
        class Storage:
            def generate_presigned_url(inner,*args,**kwargs):
                self.assertEqual(kwargs['ExpiresIn'],600);return self.location()
        with patch('scripts.arvan_transfer.configuration',return_value=POLICY),patch('scripts.arvan_transfer.client',return_value=Storage()),patch('scripts.arvan_transfer.publish',return_value='private-key'):
            stage(self.sender,check=True)
        command,data=self.sender.calls[-1]
        self.assertTrue(command.startswith('check-artifact '));self.assertNotIn('Signature',command)
        self.assertEqual(json.loads(data),{'url':self.location()})
    def test_s3_uses_private_acl_and_mismatched_size_blocks_receiver(self):
        class Storage:
            def upload_file(inner,*args,**kwargs):self.assertEqual(kwargs['ExtraArgs']['ACL'],'private')
            def head_object(inner,**kwargs):return {'ContentLength':1,'Metadata':{}}
        path,digest=prepare_zip(self.sender)
        with self.assertRaises(DownloadError):publish(Storage(),POLICY,path,digest,self.sender.digest,COMMIT)
