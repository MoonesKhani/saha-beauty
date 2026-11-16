import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from scripts.artifact_fetch import fetch,probe,valid_url,ArtifactError
from scripts.https_release import stage,DownloadError,artifact

URL='https://productionresultssa7.blob.core.windows.net/actions-results/fixture?sig=offline-only'
def digest(data):return hashlib.sha256(data).hexdigest()

class Response(BytesIO):
    def __init__(self,data,offset,total,end):
        super().__init__(data[offset:end+1]);self.status=206;self.headers={'Content-Range':f'bytes {offset}-{end}/{total}'}
    read1=BytesIO.read

class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.tar=b'offline bundle fixture; never an installable image'
        zipped=BytesIO()
        with zipfile.ZipFile(zipped,'w') as archive:
            archive.writestr('release.tar',self.tar)
            archive.writestr('release.tar.sha256',digest(self.tar)+'  release.tar\n')
        self.zip=zipped.getvalue();self.requests=[]
    def open(self,request,timeout):
        self.assertEqual(request.get_method(),'GET');self.assertEqual(timeout,8)
        self.requests.append(request)
        left,right=map(int,request.get_header('Range').removeprefix('bytes=').split('-'))
        return Response(self.zip,left,len(self.zip),right)
    def test_full_fetch_checks_zip_and_tar_and_never_installs(self):
        target=self.root/'release.tar'
        result=fetch(URL,target,digest(self.tar),len(self.tar),digest(self.zip),len(self.zip),self.open)
        self.assertTrue(result['complete']);self.assertEqual(target.read_bytes(),self.tar)
        self.assertEqual(len(self.requests),1)
    def test_partial_download_resumes_from_durable_offset(self):
        partial=self.root/('artifact-'+digest(self.zip)+'.part');partial.write_bytes(self.zip[:30])
        fetch(URL,self.root/'release.tar',digest(self.tar),len(self.tar),digest(self.zip),len(self.zip),self.open)
        self.assertEqual(self.requests[0].get_header('Range'),f'bytes=30-{len(self.zip)-1}')
    def test_bad_zip_digest_never_promotes_a_release(self):
        with self.assertRaises(ArtifactError):fetch(URL,self.root/'release.tar',digest(self.tar),len(self.tar),'0'*64,len(self.zip),self.open)
        self.assertFalse((self.root/'release.tar').exists())
    def test_wrong_tar_checksum_never_promotes_a_release(self):
        with self.assertRaises(ArtifactError):fetch(URL,self.root/'release.tar','0'*64,len(self.tar),digest(self.zip),len(self.zip),self.open)
        self.assertFalse((self.root/'release.tar').exists())
    def test_range_probe_does_not_write_a_bundle(self):
        self.assertTrue(probe(URL,len(self.zip),self.open)['https_ok'])
        self.assertEqual(list(self.root.iterdir()),[])
    def test_untrusted_hosts_credentials_redirects_and_extra_members_rejected(self):
        for url in ['http://productionresultssa7.blob.core.windows.net/private', 'https://productionresultssa7.blob.core.windows.net.evil.invalid/private', 'https://user:private@productionresultssa7.blob.core.windows.net/private','https://127.0.0.1/private','https://console.melipayamak.com/api/send/otp/private']:
            with self.assertRaises(ArtifactError):valid_url(url)
        with zipfile.ZipFile(BytesIO(self.zip)) as original:
            broken=BytesIO()
            with zipfile.ZipFile(broken,'w') as archive:
                for name in original.namelist():archive.writestr(name,original.read(name))
                archive.writestr('../outside',b'not allowed')
            self.zip=broken.getvalue()
        with self.assertRaises(ArtifactError):fetch(URL,self.root/'release.tar',digest(self.tar),len(self.tar),digest(self.zip),len(self.zip),self.open)
        self.assertFalse((self.root.parent/'outside').exists())

class ClientTests(unittest.TestCase):
    def test_old_receiver_fails_before_generating_or_sending_a_signed_link(self):
        class Sender:
            def request(self,*args,**kwargs):return {'transfer_protocol':2}
        with patch('scripts.https_release.github_request') as request:
            with self.assertRaises(DownloadError):stage(Sender(),'1','fixture')
            request.assert_not_called()
    def test_only_url_is_in_ssh_stdin_not_command_or_report(self):
        class Sender:
            commit='a'*40;digest='b'*64;size=100
            def __init__(self):self.calls=[]
            def request(self,command,data=None,timeout=None):
                self.calls.append((command,data))
                return {'artifact_fetch':True} if command=='status' else {'complete':True,'bytes':100}
        sender=Sender()
        metadata={'id':123,'digest':'sha256:'+'c'*64,'size_in_bytes':300}
        with patch('scripts.https_release.artifact',return_value=metadata),patch('scripts.https_release.github_request',return_value=URL):
            stage(sender,'1','fixture')
        command,data=sender.calls[1]
        self.assertNotIn('sig=',command);self.assertEqual(json.loads(data),{'url':URL})
    def test_artifact_must_match_approved_source(self):
        row={'name':'fixture','expired':False,'workflow_run':{'head_sha':'b'*40},'digest':'sha256:'+'c'*64,'size_in_bytes':300}
        with patch('scripts.https_release.github_request',return_value={'artifacts':[row]}):
            with self.assertRaises(DownloadError):artifact('1','fixture','a'*40)
