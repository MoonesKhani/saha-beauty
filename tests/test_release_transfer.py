"""Wire truncation and retry regressions; no SSH/network or live volumes."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.deploy_receiver import TransferStore, receive, parse_command, main as receiver_main
from scripts.deploy_release import DeploymentError, verify_bundle_file, unpack_bundle, atomic_json
from scripts.transfer_release import Sender, TransferError, TemporaryTransportError
import test_release_deployment as fixtures
SHA=fixtures.SHA
NEW=fixtures.NEW


def digest(data):return hashlib.sha256(data).hexdigest()

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=b'first chunksecond chunk'
        self.store=TransferStore(self.root/'inbox',SHA,digest(self.data),len(self.data))
    def test_eof_mid_chunk_is_rejected_and_removed(self):
        target=self.root/'chunk'
        with self.assertRaisesRegex(ValueError,'Incomplete transfer'):
            receive(BytesIO(self.data[:3]),target,len(self.data),digest(self.data))
        self.assertFalse(target.exists())
        self.assertEqual(self.store.info()['bytes'],0)
    def test_extra_byte_and_wrong_checksum_are_rejected(self):
        for data,expected in [(self.data+b'!',digest(self.data)),(self.data,'0'*64)]:
            target=self.root/'chunk'
            with self.assertRaises(ValueError):receive(BytesIO(data),target,len(self.data),expected)
            self.assertFalse(target.exists())
    def test_interruption_then_resume_keeps_verified_prefix_only(self):
        first=self.data[:8];second=self.data[8:]
        self.store.put(BytesIO(first),0,len(first),digest(first))
        with self.assertRaisesRegex(ValueError,'Incomplete transfer'):
            self.store.put(BytesIO(second[:2]),len(first),len(second),digest(second))
        self.assertEqual(self.store.info()['bytes'],8)
        result=self.store.put(BytesIO(second),8,len(second),digest(second))
        self.assertTrue(result['complete']);self.assertEqual(self.store.bundle.read_bytes(),self.data)
    def test_wrong_full_digest_never_promotes_bundle(self):
        store=TransferStore(self.root/'inbox',SHA,'0'*64,len(self.data))
        with self.assertRaisesRegex(DeploymentError,'SHA-256'):
            store.put(BytesIO(self.data),0,len(self.data),digest(self.data))
        self.assertFalse(store.bundle.exists());self.assertEqual(store.info()['bytes'],0)
    def test_lost_chunk_ack_resumes_without_duplicate_append(self):
        self.store.put(BytesIO(self.data),0,len(self.data),digest(self.data))
        # A retried stale chunk is acknowledged only after full hash recheck.
        self.assertTrue(self.store.put(BytesIO(self.data),0,len(self.data),digest(self.data))['complete'])
        self.assertEqual(self.store.bundle.read_bytes(),self.data)
    def test_partial_append_after_killed_process_is_rolled_back(self):
        self.store.partial.write_bytes(self.data[:8])
        atomic_json(self.store.folder/'append.json',{'offset':4})
        self.store.recover_append()
        self.assertEqual(self.store.partial.read_bytes(),self.data[:4])
    def test_full_append_before_rename_is_finalized_on_next_query(self):
        self.store.partial.write_bytes(self.data)
        self.assertTrue(self.store.info()['complete']);self.assertTrue(self.store.bundle.exists())
    def test_oversize_and_command_injection_are_rejected(self):
        prefix=f'upload-chunk {SHA} {digest(self.data)} {len(self.data)}'
        for command in [prefix+' 0 9999999 '+'0'*64,prefix+' 999 1 '+'0'*64,
                        f'transfer-info {SHA} '+ '0'*64+' 9999999999',
                        f'deploy-verified {SHA} '+ '0'*64+' 20; id']:
            with self.assertRaises(ValueError):parse_command(command)
    def test_real_pipe_eof_across_receiver_processes_can_resume(self):
        project=self.root/'project';project.mkdir()
        (self.root/'config.json').write_text(json.dumps({'project':str(project)}))
        program="""
import json,os,sys
from pathlib import Path
from unittest.mock import patch
from scripts import deploy_receiver as receiver
receiver.ROOT=Path(sys.argv[1])
os.environ['SSH_ORIGINAL_COMMAND']=sys.argv[2]
receiver.transaction_info=lambda store,project: {}
try:
 with patch.object(receiver.shutil,'disk_usage',return_value=type('Disk',(),{'free':8*1024**3})()):
  receiver.main()
except (ValueError,receiver.DeploymentError) as error:
 raise SystemExit(str(error))
"""
        def child(command,data=b''):
            return subprocess.run([sys.executable,'-c',program,str(self.root),command],input=data,capture_output=True)
        first=self.data[:8];second=self.data[8:]
        identity=f'{SHA} {digest(self.data)} {len(self.data)}'
        self.assertEqual(child(f'upload-chunk {identity} 0 8 {digest(first)}',first).returncode,0)
        cut=child(f'upload-chunk {identity} 8 {len(second)} {digest(second)}',second[:2])
        self.assertNotEqual(cut.returncode,0);self.assertIn(b'Incomplete transfer',cut.stderr)
        info=child('transfer-info '+identity+' 1-1')
        self.assertEqual(json.loads(info.stdout)['bytes'],8)
        self.assertEqual(child(f'upload-chunk {identity} 8 {len(second)} {digest(second)}',second).returncode,0)
        self.assertEqual(self.store.bundle.read_bytes(),self.data)

    def test_valid_protocol_commands(self):
        identity=f'{SHA} {digest(self.data)} {len(self.data)} 1-1'
        self.assertEqual(parse_command('transfer-info '+identity),('transfer-info',(SHA,digest(self.data),len(self.data),'1-1')))
        self.assertEqual(parse_command('deploy-verified '+identity)[0],'deploy-verified')
    def invoke_receiver(self,command):
        project=self.root/'project';project.mkdir(exist_ok=True)
        (self.root/'config.json').write_text(json.dumps({'project':str(project)}))
        with patch('scripts.deploy_receiver.ROOT',self.root),patch.dict('os.environ',{'SSH_ORIGINAL_COMMAND':command}):
            receiver_main()
    def test_legacy_unframed_stream_cannot_start_installation(self):
        with patch('scripts.deploy_receiver.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'Legacy unframed'):
                self.invoke_receiver('deploy '+SHA)
            run.assert_not_called()
    def test_incomplete_bundle_never_reaches_systemd_or_tar(self):
        self.store.partial.write_bytes(self.data[:3])
        with patch('scripts.deploy_receiver.subprocess.run') as run,patch('scripts.deploy_receiver.unpack_bundle') as unpack:
            with self.assertRaisesRegex(ValueError,'Bundle incomplete'):
                self.invoke_receiver(f'deploy-verified {SHA} {digest(self.data)} {len(self.data)} 1-1')
            run.assert_not_called();unpack.assert_not_called()
    def test_corrupt_completed_bundle_never_reaches_systemd_or_tar(self):
        self.store.bundle.write_bytes(b'!'*len(self.data))
        with patch('scripts.deploy_receiver.subprocess.run') as run,patch('scripts.deploy_receiver.unpack_bundle') as unpack:
            with self.assertRaisesRegex(DeploymentError,'SHA-256'):
                self.invoke_receiver(f'deploy-verified {SHA} {digest(self.data)} {len(self.data)} 1-1')
            run.assert_not_called();unpack.assert_not_called()

class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.BundleTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.bundle=self.fixture.bundle();self.data=self.bundle.read_bytes()
        self.project=self.root/'project';self.project.mkdir()
        (self.root/'config.json').write_text(json.dumps({'project':str(self.project)}))
        self.store=TransferStore(self.root/'inbox',SHA,digest(self.data),len(self.data))
        self.store.put(BytesIO(self.data),0,len(self.data),digest(self.data))
        self.command=f'deploy-verified {SHA} {digest(self.data)} {len(self.data)} 1-1'
    def invoke(self):
        with patch('scripts.deploy_receiver.ROOT',self.root),patch.dict('os.environ',{'SSH_ORIGINAL_COMMAND':self.command}),patch('sys.stdout',new=BytesIOText()):
            receiver_main()
    def test_start_ack_retry_uses_existing_unit_without_second_start(self):
        started=[]
        def run(args,**kwargs):
            if args[0]=='systemctl':
                state='loaded' if started else 'not-found'
                return subprocess.CompletedProcess(args,0 if started else 1,'LoadState='+state+'\nActiveState=active\nResult=success\n','')
            self.assertEqual(args[0],'systemd-run');started.append(args)
            return subprocess.CompletedProcess(args,0)
        with patch('scripts.deploy_receiver.subprocess.run',side_effect=run):
            self.invoke();self.invoke()
        self.assertEqual(len(started),1)
        self.assertIn('--bundle-sha256',started[0]);self.assertIn('--bundle-bytes',started[0])
        self.assertEqual(self.store.bundle.read_bytes(),self.data)
    def test_truncated_archive_with_matching_wire_hash_cannot_start_service(self):
        data=self.data[:1540]
        store=TransferStore(self.root/'inbox',SHA,digest(data),len(data))
        store.put(BytesIO(data),0,len(data),digest(data))
        self.command=f'deploy-verified {SHA} {digest(data)} {len(data)} 1-1'
        result=subprocess.CompletedProcess([],1,'LoadState=not-found\nActiveState=inactive\nResult=success\n','')
        with patch('scripts.deploy_receiver.subprocess.run',return_value=result) as run:
            with self.assertRaisesRegex(DeploymentError,'truncated release archive'):self.invoke()
            self.assertTrue(all(call.args[0][0]!='systemd-run' for call in run.call_args_list))
    def test_explicit_new_workflow_attempt_has_own_unit_but_reuses_upload(self):
        other=TransferStore(self.root/'inbox',SHA,digest(self.data),len(self.data),attempt='12-2')
        self.assertEqual(other.bundle,self.store.bundle);self.assertNotEqual(other.unit,self.store.unit)

class BytesIOText:
    def write(self,text):return len(text)
    def flush(self):pass

class BundleIntegrityTests(unittest.TestCase):
    setUp=fixtures.BundleTest.setUp
    bundle=fixtures.BundleTest.bundle
    def test_outer_size_and_hash_are_verified_before_tar_open(self):
        bundle=self.bundle();size=bundle.stat().st_size;expected=digest(bundle.read_bytes())
        verify_bundle_file(bundle,size,expected)
        with patch('tarfile.open') as tar:
            with self.assertRaisesRegex(DeploymentError,'Incomplete bundle'):
                verify_bundle_file(bundle,size+1,expected)
            with self.assertRaisesRegex(DeploymentError,'SHA-256'):
                verify_bundle_file(bundle,size,'0'*64)
            tar.assert_not_called()
    def test_truncated_tar_gives_clear_error_without_extracting(self):
        bundle=self.bundle();bundle.write_bytes(bundle.read_bytes()[:1540])
        with self.assertRaisesRegex(DeploymentError,'truncated release archive'):
            unpack_bundle(bundle,self.root/'stage',SHA)
        self.assertFalse((self.root/'stage').exists())

class FakeRemote:
    def __init__(self,root,data):
        self.store=TransferStore(root/'inbox',SHA,digest(data),len(data));self.calls=[]
        self.lose_ack=False;self.fail_start_ack=False;self.failed_install=False;self.started=0;self.state={}
    def request(self,command,data=None,timeout=60):
        mode,identity=parse_command(command);self.calls.append(mode)
        if mode=='upload-chunk':
            info=self.store.put(BytesIO(data),*identity[3:])
            if self.lose_ack:self.lose_ack=False;raise TemporaryTransportError('lost chunk ack')
            return info
        info={**self.store.info(),'service':{'LoadState':'not-found','ActiveState':'inactive'},'unit':self.store.unit,'deployment':self.state}
        if self.started:
            info['service']={'LoadState':'loaded','ActiveState':'failed' if self.failed_install else 'inactive','Result':'exit-code' if self.failed_install else 'success'}
        if mode=='transfer-info':return info
        if mode=='deploy-verified':
            if not self.started:self.started+=1
            if not self.failed_install:self.state={'phase':'healthy','current':NEW,'previous':{'image_id':'sha256:'+'1'*64},'backup':'fixture-only'}
            if self.fail_start_ack:self.fail_start_ack=False;raise TemporaryTransportError('lost start ack')
            return info
        raise AssertionError(mode)

class SenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data=b'abcd'*20;self.bundle=self.root/'release.tar';self.bundle.write_bytes(self.data)
        self.sender=Sender(['ssh'],self.bundle,SHA,self.root/'report',expected_image=NEW['image_id'],sleep=lambda _:None)
        self.remote=FakeRemote(self.root,self.data);self.sender.request=self.remote.request
    def test_lost_upload_and_start_ack_do_not_duplicate_install(self):
        self.remote.lose_ack=True;self.remote.fail_start_ack=True
        with patch('scripts.transfer_release.CHUNK_BYTES',16):self.sender.deploy()
        self.assertEqual(self.remote.store.bundle.read_bytes(),self.data)
        self.assertEqual(self.remote.started,1)
        self.assertEqual(json.loads(self.sender.report.read_text())['current']['commit'],SHA)
    def test_small_chunks_reuse_ack_and_have_short_deadlines(self):
        self.data=b'x'*(600*1024);self.bundle.write_bytes(self.data)
        sender=Sender(['ssh'],self.bundle,SHA,self.root/'report',expected_image=NEW['image_id'],sleep=lambda _:None)
        remote=FakeRemote(self.root,self.data);sent=[]
        def request(command,data=None,timeout=60):
            if command.startswith('upload-chunk'):
                sent.append((len(data),timeout))
            return remote.request(command,data,timeout)
        sender.request=request;sender.upload()
        self.assertEqual(sent,[(256*1024,90),(256*1024,90),(88*1024,90)])
        self.assertEqual(remote.calls.count('transfer-info'),1)
        self.assertEqual(remote.store.bundle.read_bytes(),self.data)

    def test_file_backed_stdin_delivers_eof_without_parent_input_pipe(self):
        sender=Sender([sys.executable,'-c',
            'import sys,json,hashlib; data=sys.stdin.buffer.read(); print(json.dumps({"bytes":len(data),"digest":hashlib.sha256(data).hexdigest()}))'],
            self.bundle,SHA,self.root/'report',expected_image=NEW['image_id'])
        # Above the observed 2 MiB boundary: this checks local EOF/pipe behavior,
        # without claiming to reproduce the production network stall.
        data=b'x'*(3*1024**2)
        result=sender.request('fixture',data,timeout=5)
        self.assertEqual(result,{'bytes':len(data),'digest':digest(data)})
        empty=sender.request('fixture',timeout=5)
        self.assertEqual(empty['bytes'],0)

    def test_invalid_ack_stops_before_installation(self):
        self.sender.request=lambda *args,**kwargs: {'bytes':0,'complete':False,'protocol':2}
        with self.assertRaisesRegex(TransferError,'acknowledgement'):self.sender.deploy()
        self.assertFalse(self.sender.report.exists())

    def test_same_commit_with_other_image_cannot_report_success(self):
        info={'deployment':{'phase':'healthy','current':{**NEW,'image_id':'sha256:'+'9'*64}}}
        self.assertIsNone(self.sender.healthy_report(info))

    def test_failed_installation_is_not_blindly_retried(self):
        self.remote.failed_install=True
        with self.assertRaisesRegex(TransferError,'Inspect journalctl'):self.sender.deploy()
        self.assertEqual(self.remote.started,1);self.assertFalse(self.sender.report.exists())
    def test_failed_unit_cannot_inherit_old_healthy_state_for_same_image(self):
        self.remote.failed_install=True
        self.remote.state={'phase':'healthy','current':NEW}
        with self.assertRaisesRegex(TransferError,'Installation failed'):self.sender.deploy()
        self.assertFalse(self.sender.report.exists())

    def test_repeated_transfer_failure_never_requests_installation(self):
        def request(command,data=None,timeout=60):
            if command.startswith('upload-chunk'):raise TemporaryTransportError('interrupted')
            return self.remote.request(command,data,timeout)
        self.sender.request=request
        with self.assertRaisesRegex(TransferError,'retries exhausted'):self.sender.deploy()
        self.assertEqual(self.remote.started,0);self.assertFalse(self.sender.report.exists())
    def test_ssh_timeout_and_connection_loss_are_retryable(self):
        sender=Sender(['ssh'],self.bundle,SHA,self.root/'report',expected_image=NEW['image_id'])
        with patch('scripts.transfer_release.subprocess.run',side_effect=subprocess.TimeoutExpired('ssh',60)):
            with self.assertRaises(TemporaryTransportError):sender.request('status')
        with patch('scripts.transfer_release.subprocess.run',return_value=subprocess.CompletedProcess('ssh',255,b'',b'connection reset')):
            with self.assertRaises(TemporaryTransportError):sender.request('status')
    def test_permanent_receiver_rejection_is_not_retried(self):
        sender=Sender(['ssh'],self.bundle,SHA,self.root/'report',expected_image=NEW['image_id'])
        with patch('scripts.transfer_release.subprocess.run',return_value=subprocess.CompletedProcess('ssh',1,b'',b'checksum mismatch')):
            with self.assertRaisesRegex(TransferError,'Receiver rejected'):sender.request('status')

if __name__=='__main__':unittest.main()
