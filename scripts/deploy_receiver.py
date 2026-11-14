"""Forced-command SSH endpoint. No shell, arbitrary paths, forwarding, or registry access."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

MAX_BUNDLE=2*1024**3
ROOT=Path('/opt/saha-deploy')

def parse_command(command):
    if command=='status':return 'status',None
    match=re.fullmatch(r'deploy ([0-9a-f]{40})',command)
    if match:return 'deploy',match[1]
    match=re.fullmatch(r'(rollback|site) (sha256:[0-9a-f]{64})',command)
    if match:return match[1],match[2]
    raise ValueError('Only status or an exact approved deploy/rollback identity is accepted')

def receive(stream,target,limit=MAX_BUNDLE):
    size=0
    with target.open('xb') as output:
        os.chmod(target,0o600)
        while data:=stream.read(1024*1024):
            size+=len(data)
            if size>limit:raise ValueError('Bundle too large')
            output.write(data)
    if not size:raise ValueError('Empty release bundle')

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
        subprocess.run(['bash',str(updater),'--status','--project',str(project)],check=True);return
    inbox=ROOT/'inbox';inbox.mkdir(exist_ok=True,mode=0o700)
    if shutil.disk_usage(inbox).free<4*1024**3:raise ValueError('Insufficient disk for receiving a release')
    with tempfile.TemporaryDirectory(prefix='incoming-',dir=inbox) as temporary:
        arguments=['bash',str(updater),'--release' if operation=='deploy' else '--rollback','--project',str(project)]
        if operation=='deploy':
            bundle=Path(temporary)/'release.tar';receive(sys.stdin.buffer,bundle)
            arguments+=['--bundle',str(bundle),'--commit',identity]
        else:arguments+=['--rollback-image',identity]
        # The transaction keeps running under systemd even if the SSH connection drops.
        unit='saha-release-'+os.path.basename(temporary)
        result=subprocess.run(['systemd-run','--quiet','--wait','--collect','--unit',unit,'--property=Type=exec',*arguments])
        if result.returncode:raise ValueError('Release failed; inspect journalctl -u '+unit+' and request deployment status')
        subprocess.run(['bash',str(updater),'--status','--project',str(project)],check=True)
if __name__=='__main__':
    try:main()
    except (ValueError,subprocess.CalledProcessError) as error:raise SystemExit(str(error)) from None
