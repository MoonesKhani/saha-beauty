"""Resumable verified SSH upload; installation is a separate, idempotent command.

Uses the same pinned SSH configuration as approved_transport.sh. Never retries
an application failure or an uncertain switch by starting another transaction.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

CHUNK_BYTES=256*1024
CHUNK_TIMEOUT=90

class TransferError(RuntimeError):pass
class TemporaryTransportError(TransferError):pass

class Sender:
    def __init__(self,ssh,bundle,commit,report,*,expected_image,attempt='1-1',attempts=2,sleep=time.sleep,clock=time.monotonic):
        self.ssh=ssh;self.bundle=Path(bundle);self.commit=commit;self.report=Path(report)
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',expected_image):raise TransferError('Invalid expected image identity')
        self.expected_image=expected_image
        self.size=self.bundle.stat().st_size
        with self.bundle.open('rb') as source:self.digest=hashlib.file_digest(source,'sha256').hexdigest()
        if not re.fullmatch(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,3}',attempt):raise TransferError('Invalid workflow attempt identity')
        self.identity=f'{commit} {self.digest} {self.size}'
        self.transaction_identity=self.identity+' '+attempt
        self.attempts=attempts;self.sleep=sleep;self.clock=clock
    def request(self,command,data=None,timeout=60):
        try:
            # A regular-file stdin gives SSH its EOF directly and removes the
            # parent-to-SSH pipe from bulk transfer. communicate still drains
            # stdout/stderr; status commands receive no inherited stdin.
            with ExitStack() as stack:
                source=subprocess.DEVNULL
                if data is not None:
                    source=stack.enter_context(tempfile.TemporaryFile())
                    source.write(data);source.seek(0)
                result=subprocess.run(self.ssh+[command],stdin=source,capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise TemporaryTransportError('SSH timed out; querying the durable remote offset before retry') from error
        if result.returncode:
            # No secret/environment output. Receiver diagnostics contain only
            # bounded transfer metadata; SSH diagnostics are kept by the runner.
            diagnostic=result.stderr.decode(errors='replace')[-2000:].strip()
            if result.returncode==255 or 'Transfer busy;' in diagnostic:
                raise TemporaryTransportError(f'SSH transfer interrupted (exit {result.returncode}): {diagnostic}')
            raise TransferError(f'Receiver rejected operation (exit {result.returncode}): {diagnostic}')
        try:return json.loads(result.stdout)
        except (ValueError,UnicodeDecodeError) as error:raise TransferError('Receiver returned an invalid JSON report; no installation retry') from error
    def query(self):
        for attempt in range(self.attempts):
            try:
                info=self.request('transfer-info '+self.transaction_identity)
                if info.get('protocol')!=2:raise TransferError('Receiver protocol 2 required; update /opt/saha-deploy before deploying')
                return info
            except TemporaryTransportError as error:
                if attempt+1==self.attempts:raise
                print(f'{error}; status retry {attempt+1}/{self.attempts}',file=sys.stderr,flush=True)
                self.sleep(min(5*(attempt+1),20))
    def upload(self):
        deadline=self.clock()+50*60
        failures=0;info=None
        while True:
            if self.clock()>deadline:raise TransferError('Upload time budget exceeded; installation NOT requested. Rerun after fixing connectivity; verified chunks are retained')
            if info is None:info=self.query()
            offset=info.get('bytes')
            if type(offset) is not int or not 0<=offset<=self.size:raise TransferError('Invalid remote transfer offset')
            if info.get('complete'):
                if offset!=self.size:raise TransferError('Invalid complete transfer size')
                print(f'Upload verified: {self.size} bytes, SHA-256 matched on server',flush=True)
                return
            if offset==self.size:raise TransferError('Remote full-length file was not verified; installation blocked')
            with self.bundle.open('rb') as source:
                source.seek(offset);chunk=source.read(CHUNK_BYTES)
            chunk_hash=hashlib.sha256(chunk).hexdigest()
            command=f'upload-chunk {self.identity} {offset} {len(chunk)} {chunk_hash}'
            try:
                print(f'Uploading chunk: offset={offset}, bytes={len(chunk)}, timeout={CHUNK_TIMEOUT}s',flush=True)
                acknowledgement=self.request(command,chunk,timeout=CHUNK_TIMEOUT)
                if acknowledgement.get('protocol')!=2 or acknowledgement.get('bytes')!=offset+len(chunk):
                    raise TransferError('Invalid chunk acknowledgement; installation blocked')
                info=acknowledgement # Reuse the verified ACK; query again only after an uncertain send.
                failures=0
                print(f'Upload progress: {offset+len(chunk)}/{self.size} bytes ({100*(offset+len(chunk))/self.size:.1f}%)',flush=True)
            except TemporaryTransportError as error:
                info=None
                failures+=1
                if failures>=self.attempts:raise TransferError('Upload retries exhausted; installation NOT requested. Verified chunks retained for resume') from error
                print(f'{error}; chunk retry {failures}/{self.attempts}; checking committed offset',file=sys.stderr,flush=True)
                self.sleep(min(failures*5,20))
    def healthy_report(self,info):
        state=info.get('deployment') or {}
        current=state.get('current') or {}
        return state if state.get('phase')=='healthy' and current.get('commit')==self.commit and current.get('image_id')==self.expected_image else None
    def deploy(self):
        self.upload()
        # Same deterministic unit: retries of the start request only reconnect
        # to an existing transaction; they never create another installation.
        for attempt in range(self.attempts):
            try:
                self.request('deploy-verified '+self.transaction_identity,timeout=180)
                break
            except TemporaryTransportError as error:
                info=self.query()
                if self.healthy_report(info):break
                if info.get('service',{}).get('LoadState')=='loaded':break
                if attempt+1==self.attempts:raise
                print(f'{error}; start request retry after read-only status',file=sys.stderr,flush=True)
                self.sleep(5)
        deadline=self.clock()+25*60
        while self.clock()<deadline:
            info=self.query();state=self.healthy_report(info)
            active=info.get('service',{}).get('ActiveState')
            # A failed attempt cannot inherit an older healthy state for the same image.
            if active=='failed':
                raise TransferError(f"Installation failed (unit {info.get('unit')}, phase {(info.get('deployment') or {}).get('phase','not-started')}). Inspect journalctl; no automatic installation retry")
            # Do not accept a stale healthy report while a service still runs.
            if state and active not in ('active','activating','deactivating'):
                self.report.write_text(json.dumps(state)+'\n')
                print('Installation healthy; exact approved commit confirmed',flush=True);return
            if active in ('failed','inactive'):
                raise TransferError(f"Installation did not finish healthy (unit {info.get('unit')}, result {info.get('service',{}).get('Result')}, phase {(info.get('deployment') or {}).get('phase','not-started')}). Inspect journalctl for this unit; do not blindly retry installation")
            print(f"Installation status: {active or 'unknown'}; unit {info.get('unit')}",flush=True)
            self.sleep(15)
        raise TransferError('Installation status deadline exceeded. Transaction may still run; read status before any retry')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--attempt',required=True);parser.add_argument('--bundle',required=True);parser.add_argument('--commit',required=True);parser.add_argument('--report',required=True)
    parser.add_argument('ssh',nargs=argparse.REMAINDER)
    args=parser.parse_args();ssh=args.ssh[1:] if args.ssh[:1]==['--'] else args.ssh
    if not ssh:parser.error('SSH command required')
    try:
        with tarfile.open(args.bundle,'r:') as archive:
            member=archive.getmember('manifest.json')
            if not member.isfile() or member.size>65536:raise TransferError('Invalid artifact manifest')
            manifest=json.load(archive.extractfile(member))
        if manifest.get('commit')!=args.commit:raise TransferError('Artifact commit differs from approval')
    except (tarfile.TarError,KeyError,ValueError) as error:
        raise TransferError('Invalid local artifact; upload and installation blocked') from error
    Sender(ssh,args.bundle,args.commit,args.report,expected_image=manifest.get('image_id',''),attempt=args.attempt).deploy()
if __name__=='__main__':
    try:main()
    except TransferError as error:raise SystemExit(str(error)) from None
