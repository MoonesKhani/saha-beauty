"""Forced-command SSH endpoint. No shell, arbitrary paths, forwarding, or registry access."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from .deploy_release import DeploymentError, verify_bundle_file, unpack_bundle, read_state, atomic_json
except ImportError:
    from deploy_release import DeploymentError, verify_bundle_file, unpack_bundle, read_state, atomic_json

CHUNK_BYTES=4*1024**2
MAX_BUNDLE=2*1024**3
ROOT=Path('/opt/saha-deploy')

def parse_command(command):
    if command=='status':return 'status',None
    match=re.fullmatch(r'(transfer-info|deploy-verified) ([0-9a-f]{40}) ([0-9a-f]{64}) ([1-9][0-9]{0,9}) ([1-9][0-9]{0,19}-[1-9][0-9]{0,3})',command)
    if match:
        mode,commit,digest,size,attempt=match.groups()
        if int(size)>MAX_BUNDLE:raise ValueError('Bundle too large')
        return mode,(commit,digest,int(size),attempt)
    match=re.fullmatch(r'upload-chunk ([0-9a-f]{40}) ([0-9a-f]{64}) ([1-9][0-9]{0,9}) ([0-9]{1,10}) ([1-9][0-9]{0,7}) ([0-9a-f]{64})',command)
    if match:
        commit,digest,size,offset,length,chunk_hash=match.groups()
        size,offset,length=map(int,(size,offset,length))
        if size>MAX_BUNDLE or length>CHUNK_BYTES or offset+length>size:raise ValueError('Invalid chunk bounds')
        return 'upload-chunk',(commit,digest,size,offset,length,chunk_hash)
    match=re.fullmatch(r'deploy ([0-9a-f]{40})',command)
    if match:return 'deploy',match[1]
    match=re.fullmatch(r'(rollback|site) (sha256:[0-9a-f]{64})',command)
    if match:return match[1],match[2]
    raise ValueError('Only status or an exact approved deploy/rollback identity is accepted')

def receive(stream,target,expected_bytes,expected_sha256,limit=MAX_BUNDLE):
    """EOF alone is never evidence that a transmission is complete."""
    if not 0 < expected_bytes <= limit:raise ValueError('Invalid transfer size')
    size=0;digest=hashlib.sha256();created=False
    try:
        with target.open('xb') as output:
            created=True
            os.chmod(target,0o600)
            while size<expected_bytes:
                data=stream.read(min(1024*1024,expected_bytes-size))
                if not data:raise ValueError(f'Incomplete transfer: expected {expected_bytes} bytes, received {size}; installation blocked')
                size+=len(data);digest.update(data);output.write(data)
            if stream.read(1):raise ValueError('Transfer exceeded declared size; installation blocked')
            output.flush();os.fsync(output.fileno())
        if digest.hexdigest()!=expected_sha256:raise ValueError('Transfer checksum mismatch; installation blocked')
    except BaseException:
        if created:target.unlink(missing_ok=True)
        raise

class TransferStore:
    """Private resumable chunks, isolated from the production tree and its volumes."""
    def __init__(self,inbox,commit,digest,size,attempt='1-1'):
        self.commit=commit;self.digest=digest;self.size=size
        self.folder=inbox/(commit+'-'+digest);self.folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.partial=self.folder/'release.part';self.bundle=self.folder/'release.tar'
        self.unit='saha-release-'+hashlib.sha256((commit+digest+attempt).encode()).hexdigest()[:32]
    def lock(self):
        file=(self.folder/'transfer.lock').open('a')
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            file.close();raise ValueError('Transfer busy; retry this chunk') from None
        return file
    def info(self):
        if self.bundle.exists():
            verify_bundle_file(self.bundle,self.size,self.digest)
            return {'bytes':self.size,'complete':True,'protocol':2}
        count=self.partial.stat().st_size if self.partial.exists() else 0
        if count==self.size:
            try:verify_bundle_file(self.partial,self.size,self.digest)
            except DeploymentError:
                self.partial.unlink();raise
            os.replace(self.partial,self.bundle)
            return {'bytes':self.size,'complete':True,'protocol':2}
        if count>self.size:raise ValueError('Invalid staged size; installation blocked')
        return {'bytes':count,'complete':False,'protocol':2}
    def put(self,stream,offset,length,chunk_hash):
        with self.lock(),tempfile.TemporaryDirectory(prefix='chunk-',dir=self.folder) as temporary:
            status=self.info()
            if status['complete']:return status
            if status['bytes']!=offset:raise ValueError('Chunk offset changed; query transfer-info and resume')
            chunk=Path(temporary)/'data'
            receive(stream,chunk,length,chunk_hash,limit=CHUNK_BYTES)
            # Commit a verified chunk durably. A killed append is rolled back by
            # the small journal before the next query, so resume never trusts a torn chunk.
            journal=self.folder/'append.json'
            atomic_json(journal,{'offset':offset})
            with self.partial.open('ab') as output,chunk.open('rb') as source:
                os.chmod(self.partial,0o600);shutil.copyfileobj(source,output)
                output.flush();os.fsync(output.fileno())
            journal.unlink()
            if self.partial.stat().st_size==self.size:
                try:verify_bundle_file(self.partial,self.size,self.digest)
                except DeploymentError:
                    self.partial.unlink();raise
                os.replace(self.partial,self.bundle)
            return self.info()
    def recover_append(self):
        journal=self.folder/'append.json'
        if journal.exists():
            offset=json.loads(journal.read_text())['offset']
            if self.partial.exists():
                with self.partial.open('r+b') as output:output.truncate(offset);output.flush();os.fsync(output.fileno())
            elif offset:
                raise ValueError('Missing verified transfer prefix; installation blocked')
            journal.unlink()

def transaction_info(store,project):
    result=subprocess.run(['systemctl','show',store.unit,'--property=LoadState,ActiveState,Result','--no-pager'],capture_output=True,text=True,check=False)
    properties=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode and properties.get('LoadState')!='not-found':
        raise ValueError('Cannot read release service state; installation blocked')
    return {'unit':store.unit,'service':properties,'deployment':read_state(project/'.deploy/state.json')}


def export_site(project,identity,staging_root,stdout=None):
    state_path=project/'.deploy/state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    records=[state.get('current') or {},state.get('previous') or {}]
    record=next((r for r in records if r.get('image_id')==identity),None)
    if not record:raise ValueError('Only a retained current/previous site image can be exported')
    with tempfile.TemporaryDirectory(prefix='site-',dir=staging_root) as directory:
        folder=Path(directory);container=None
        try:
            container=subprocess.check_output(['docker','create','--pull=never',identity]).decode().strip()
            subprocess.run(['docker','cp',container+':/app/frontend/dist/.',str(folder)],check=True,stdout=subprocess.DEVNULL)
            (folder/'release.json').write_text(json.dumps({'image_id':identity,'commit':record.get('commit')})+'\n')
            subprocess.run(['tar','-C',str(folder),'-czf','-','.'],check=True,stdout=stdout)
        finally:
            if container:subprocess.run(['docker','rm',container],check=False,stdout=subprocess.DEVNULL)


def main():
    os.umask(0o077)
    operation,identity=parse_command(os.environ.get('SSH_ORIGINAL_COMMAND',''))
    config=json.loads((ROOT/'config.json').read_text())
    project=Path(config['project']).resolve()
    updater=ROOT/'server-update.sh'
    if operation=='site':
        export_site(project,identity,ROOT);return
    if operation=='status':
        print(json.dumps({**read_state(project/'.deploy/state.json'),'transfer_protocol':2},sort_keys=True));return
    if operation=='deploy':
        raise ValueError('Legacy unframed deploy disabled: upgrade the runner to verified transfer protocol 2; installation NOT started')
    inbox=ROOT/'inbox';inbox.mkdir(exist_ok=True,mode=0o700)
    if operation in ('transfer-info','upload-chunk','deploy-verified'):
        store=TransferStore(inbox,*identity[:3],attempt=identity[3] if operation!='upload-chunk' else '1-1')
        with store.lock():store.recover_append()
        if operation=='upload-chunk':
            if shutil.disk_usage(inbox).free<4*1024**3:raise ValueError('Insufficient disk for receiving a release')
            print(json.dumps(store.put(sys.stdin.buffer,*identity[3:])));return
        if operation=='transfer-info':
            with store.lock():status=store.info()
            print(json.dumps({**status,**transaction_info(store,project)}));return
        # Starting installation requires a whole-file hash AND a structurally
        # valid archive. Never start systemd for an incomplete upload.
        with store.lock():
            if not store.info()['complete']:raise ValueError('Bundle incomplete; installation NOT started; resume upload')
            verify_bundle_file(store.bundle,store.size,store.digest)
            transaction=transaction_info(store,project)
            if transaction['service'].get('LoadState')=='not-found':
                with tempfile.TemporaryDirectory(prefix='validate-',dir=store.folder) as temporary:
                    unpack_bundle(store.bundle,Path(temporary)/'bundle',store.commit)
                arguments=['bash',str(updater),'--release','--project',str(project),'--bundle',str(store.bundle),'--commit',store.commit,'--bundle-bytes',str(store.size),'--bundle-sha256',store.digest]
                # Start only once. The deterministic retained unit lets a runner
                # reconnect/poll without repeating an uncertain installation.
                subprocess.run(['systemd-run','--quiet','--unit',store.unit,'--property=Type=exec','--property=RuntimeMaxSec=1200','--property=TimeoutStopSec=90',*arguments],check=True)
            print(json.dumps(transaction_info(store,project)));return

    if shutil.disk_usage(inbox).free<4*1024**3:raise ValueError('Insufficient disk for receiving a release')
    with tempfile.TemporaryDirectory(prefix='incoming-',dir=inbox) as temporary:
        arguments=['bash',str(updater),'--rollback','--project',str(project)]
        arguments+=['--rollback-image',identity]
        # The transaction keeps running under systemd even if the SSH connection drops.
        unit='saha-release-'+os.path.basename(temporary)
        result=subprocess.run(['systemd-run','--quiet','--wait','--collect','--unit',unit,'--property=Type=exec','--property=RuntimeMaxSec=1200','--property=TimeoutStopSec=90',*arguments])
        if result.returncode:raise ValueError('Release failed; inspect journalctl -u '+unit+' and request deployment status')
        subprocess.run(['bash',str(updater),'--status','--project',str(project)],check=True)
if __name__=='__main__':
    try:main()
    except OSError as error:raise SystemExit(f'Receiver filesystem/process error (errno {error.errno}); installation not confirmed; read status before retry') from None
    except (ValueError,DeploymentError,subprocess.CalledProcessError) as error:raise SystemExit(str(error)) from None
