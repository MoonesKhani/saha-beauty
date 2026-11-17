"""Explicit opt-in rehearsal on UUID Docker volumes. Never touches live data."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.deploy_release import ComposeEngine,DeploymentError,read_state,unpack_bundle
from scripts.deploy_otp_migration import MaintenanceEngine,maintain,validate_recovery,OLD,NEW,ENVIRONMENT
from scripts.package_release import digest
ROOT=Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('SAHA_RUN_DOCKER_DEPLOY_TEST')!='1':raise SystemExit('Disposable Docker test requires opt-in')
    commit=os.environ['SAHA_TEST_IMAGE_COMMIT'];bundle=Path(os.environ['SAHA_TEST_RELEASE_BUNDLE'])
    name='saha-otp-test-'+uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='saha-otp-test-') as temporary:
        root=Path(temporary);project=root/'project';project.mkdir();stage=root/'stage';stage.mkdir()
        manifest,_=unpack_bundle(bundle,stage/'bundle',commit);recovery=validate_recovery(manifest)
        primary={k:manifest[k] for k in ['commit','image_id','database_revision']}
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        current_compose=(ROOT/'compose.yaml').read_text().replace('127.0.0.1:8000:8000',f'127.0.0.1:{port}:8000')
        legacy_compose='\n'.join(line for line in current_compose.splitlines() if not any(line.lstrip().startswith(key+':') for key in ENVIRONMENT))+'\n'
        (project/'compose.yaml').write_text(legacy_compose)
        token=secrets.token_hex(32)
        (project/'.env').write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nADMIN_API_TOKEN='+token+'\nSAHA_BOOKING_ENABLED=1\nMELIPAYAMAK_API_KEY=offline-fixture-not-a-real-key\nSAHA_OTP_SECRET='+secrets.token_hex(32)+'\n')
        original_env=(project/'.env').read_bytes()
        overlay=project/'initial.json';overlay.write_text(json.dumps({'services':{'app':{'image':recovery['image_id'],'pull_policy':'never','command':['python','-m','uvicorn','backend.app.main:app','--host','0.0.0.0','--port','8000']}}}))
        compose=['docker','compose','--project-directory',str(project),'--project-name',name,'-f',str(project/'compose.yaml'),'-f',str(overlay)]
        def run(args):return subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
        def api(path):
            request=urllib.request.Request(f'http://127.0.0.1:{port}'+path)
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:return json.load(response)
        try:
            run(compose+['up','-d','--wait','--wait-timeout','60','--pull','never','db'])
            init="from alembic.config import Config; from alembic import command; command.upgrade(Config('database/alembic.ini'),'0004_packages')"
            run(compose+['run','--rm','--no-deps','--pull','never','--entrypoint','python','app','-c',init])
            run(compose+['run','--rm','--no-deps','--pull','never','--entrypoint','python','app','-m','backend.app.cli','seed'])
            run(compose+['up','-d','--no-build','--pull','never','app'])
            for _ in range(30):
                try:
                    if api('/api/v1/health/ready')['status']=='ok':break
                except Exception:time.sleep(1)
            else:raise AssertionError('Recovery not ready on schema 0004')
            # Reproduce production: Compose now declares OTP keys, but the
            # still-running legacy container was created without those keys.
            (project/'compose.yaml').write_text(current_compose)
            try:ComposeEngine(project,stage)
            except DeploymentError:pass
            else:raise AssertionError('Normal release must reject the new settings')
            assert not (project/'.deploy/state.json').exists()
            assert not (project/'backups').exists()
            engine=MaintenanceEngine(project,stage)
            assert engine.database_revision()==OLD
            db_id=engine.run(compose+['ps','-q','db'],'fixture database ID')
            run(compose+['exec','-T','app','sh','-c','printf owner-file > /app/var/owner-fixture.txt'])
            # Data committed after backups must survive image recovery as well.
            class FailedCandidate(MaintenanceEngine):
                def migrate(self,record):
                    super().migrate(record)
                    self.run(self.compose()+['exec','-T','db','psql','-U','saha','-d','saha','-c',"CREATE TABLE owner_fixture (id integer PRIMARY KEY, value text); INSERT INTO owner_fixture VALUES (1,'after-backup')"],'fixture after backup')
                def healthy(self,record):
                    super().healthy(record)
                    if record['image_id']==primary['image_id']:raise DeploymentError('simulated failed candidate check')
            failing=FailedCandidate(project,stage)
            try:maintain(failing,project/'.deploy/state.json',primary,recovery)
            except DeploymentError:pass
            else:raise AssertionError('Failed candidate must stop')
            state=read_state(project/'.deploy/state.json')
            assert state['phase']=='otp_maintenance_stopped' and state['current']['image_id']==recovery['image_id']
            assert engine.database_revision()==NEW
            check=MaintenanceEngine(project,stage)
            check.healthy(recovery)
            assert check.run(check.compose()+['exec','-T','db','psql','-U','saha','-d','saha','-Atqc','SELECT value FROM owner_fixture WHERE id=1'],'check durable fixture')=='after-backup'
            # Exact same approved maintenance can resume safely from retained schema 0005.
            run([sys.executable,str(ROOT/'scripts/deploy_otp_migration.py'),'--apply','--confirmation','MIGRATE OTP '+commit,'--project',str(project),'--bundle',str(bundle),'--commit',commit,'--bundle-bytes',str(bundle.stat().st_size),'--bundle-sha256',digest(bundle)])
            final=MaintenanceEngine(project,stage);final.healthy(primary)
            assert final.run(final.compose()+['ps','-q','db'],'unchanged database ID')==db_id
            assert final.run(final.compose()+['exec','-T','app','cat','/app/var/owner-fixture.txt'],'unchanged uploads')=='owner-file'
            assert (project/'.env').read_bytes()==original_env
            assert api('/api/v1/auth/capabilities')['enabled'] is False
            assert list((project/'backups').glob('*/database.dump'))
            print('OTP rehearsal: 0004/0005 readiness, verified backups, failed-health recovery, safe resume, DB/uploads/env preserved; no SMS')
        finally:
            # Only volumes created by this UUID project are removed.
            subprocess.run(compose+['down','--volumes','--remove-orphans'],check=False,stdout=subprocess.DEVNULL)
if __name__=='__main__':main()
