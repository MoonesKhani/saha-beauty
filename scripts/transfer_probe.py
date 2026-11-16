"""Bounded protocol-2 transfer diagnostics. Never invokes a deployment command."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

try:
    from .deploy_receiver import parse_command
except ImportError:
    from deploy_receiver import parse_command

SAMPLE_BYTES=32*1024

class ProbeError(RuntimeError):pass

def without_control_options(ssh):
    result=[];index=0
    while index<len(ssh):
        if ssh[index]=='-o' and index+1<len(ssh) and ssh[index+1].split('=',1)[0] in ('ControlMaster','ControlPersist','ControlPath'):
            index+=2;continue
        result.append(ssh[index]);index+=1
    return result

class Probe:
    def __init__(self,ssh,commit,clock=time.monotonic):
        if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Exact source SHA required')
        self.ssh=without_control_options(ssh);self.commit=commit;self.clock=clock;self.deadline=clock()+90

    def call(self,ssh,command,data=None):
        operation,identity=parse_command(command)
        if operation not in ('status','transfer-info','upload-chunk'):raise ValueError('Probe cannot install or export a release')
        if operation!='status' and identity[2]>SAMPLE_BYTES:raise ValueError('Probe sample exceeds its fixed limit')
        if data is not None and len(data)>SAMPLE_BYTES:raise ValueError('Probe sample too large')
        remaining=self.deadline-self.clock()
        if remaining<=0:raise ProbeError('probe_budget_exhausted')
        start=self.clock()
        try:
            with tempfile.TemporaryFile() as source:
                if data is not None:source.write(data);source.seek(0)
                result=subprocess.run(ssh+[command],stdin=source,capture_output=True,timeout=min(12,remaining))
        except subprocess.TimeoutExpired:raise ProbeError('timeout') from None
        if result.returncode:
            error=result.stderr.decode(errors='replace')
            kind='multiplex_broken_pipe' if 'Broken pipe' in error else 'host_key_rejected' if 'Host key verification failed' in error else 'authentication_rejected' if 'Permission denied' in error else 'ssh_or_receiver_error'
            raise ProbeError(kind)
        try:report=json.loads(result.stdout)
        except (ValueError,UnicodeDecodeError):raise ProbeError('invalid_receiver_report') from None
        return report,round(self.clock()-start,3)

    def close_master(self,socket):
        try:subprocess.run(self.ssh[:-1]+['-S',str(socket),'-O','exit',self.ssh[-1]],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        except (OSError,subprocess.TimeoutExpired):pass

    def mode(self,name,socket):
        options=['-o','ControlMaster=no','-o','ControlPath=none']
        if name!='fresh':
            options=['-o','ControlMaster=auto' if name=='auto' else 'ControlMaster=no','-o','ControlPersist=60','-o','ControlPath='+str(socket)]
        ssh=self.ssh[:-1]+options+[self.ssh[-1]]
        result={'mode':name,'sample_bytes':SAMPLE_BYTES}
        try:
            if name=='dedicated':
                remaining=self.deadline-self.clock()
                if remaining<=0:raise ProbeError('probe_budget_exhausted')
                # Detach the master from captured pipes before issuing any command.
                bootstrap=self.ssh[:-1]+['-M','-N','-f','-o','ControlPersist=60','-o','ControlPath='+str(socket),self.ssh[-1]]
                try:r=subprocess.run(bootstrap,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=min(12,remaining))
                except subprocess.TimeoutExpired:raise ProbeError('master_start_timeout') from None
                if r.returncode:raise ProbeError('master_start_failed')
            _,elapsed=self.call(ssh,'status');result['status_seconds']=elapsed
            payload=__import__('os').urandom(SAMPLE_BYTES);digest=hashlib.sha256(payload).hexdigest()
            identity=f'{self.commit} {digest} {len(payload)}'
            info,elapsed=self.call(ssh,'transfer-info '+identity+' 1-1');result['query_seconds']=elapsed
            if info.get('protocol')!=2 or info.get('bytes')!=0:raise ProbeError('unexpected_transfer_state')
            reply,elapsed=self.call(ssh,f'upload-chunk {identity} 0 {len(payload)} {digest}',payload)
            if reply.get('protocol')!=2 or reply.get('bytes')!=len(payload) or not reply.get('complete'):raise ProbeError('sample_verification_failed')
            result.update(ok=True,upload_seconds=elapsed,bytes_per_second=round(len(payload)/max(elapsed,.001)))
        except ProbeError as error:result.update(ok=False,error=str(error))
        finally:
            if name!='fresh':self.close_master(socket)
        return result

    def run(self):
        with tempfile.TemporaryDirectory(prefix='saha-transfer-probe-') as temporary:
            results=[self.mode(name,Path(temporary)/name) for name in ('fresh','auto','dedicated')]
        return {'source':self.commit,'results':results,'installation_requested':False,'max_staged_bytes':3*SAMPLE_BYTES}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--commit',required=True);parser.add_argument('ssh',nargs=argparse.REMAINDER)
    args=parser.parse_args();ssh=args.ssh[1:] if args.ssh[:1]==['--'] else args.ssh
    if not ssh:parser.error('SSH transport required')
    report=Probe(ssh,args.commit).run();print(json.dumps(report,sort_keys=True))
    if not any(item.get('ok') for item in report['results']):raise SystemExit(1)
