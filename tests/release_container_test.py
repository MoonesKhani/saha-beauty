"""Opt-in disposable Docker/PG integration; never uses the production checkout or data."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from uuid import uuid4
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.package_release import package, digest

ROOT=Path(__file__).resolve().parents[1]
def main():
    if os.environ.get('SAHA_RUN_DOCKER_DEPLOY_TEST')!='1':raise SystemExit('Set SAHA_RUN_DOCKER_DEPLOY_TEST=1 to run isolated Docker tests')
    initial=os.environ['SAHA_TEST_IMAGE_COMMIT'];b='b'*40;c='c'*40
    name='saha-test-'+uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='saha-docker-test-') as temporary:
        root=Path(temporary);project=root/'project';project.mkdir();token=secrets.token_hex(32)
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        (project/'compose.yaml').write_text((ROOT/'compose.yaml').read_text().replace('127.0.0.1:8000:8000',f'127.0.0.1:{port}:8000'))
        (project/'.env').write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nADMIN_API_TOKEN='+token+'\nSAHA_BOOKING_ENABLED=1\n')
        original_env=(project/'.env').read_bytes()
        overlay=project/'initial.json';overlay.write_text(json.dumps({'services':{'app':{'image':'saha-release:'+initial,'pull_policy':'never'}}}))
        compose=['docker','compose','--project-directory',str(project),'--project-name',name,'-f',str(project/'compose.yaml'),'-f',str(overlay)]
        def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
        def api(path,body=None,method=None,binary=None,content_type='application/json'):
            request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=binary if binary is not None else json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':content_type})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request,timeout=5) as response:
                data=response.read()
                return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data
        try:
            run(['docker','pull','postgres:16-alpine'])
            run(compose+['up','-d','--no-build','--pull','never','db','app'])
            for _ in range(60):
                try:
                    if api('/api/v1/health/ready')['status']=='ok':break
                except Exception:time.sleep(1)
            else:raise AssertionError('Isolated app did not become ready')
            # Two derived images reuse all local layers; no registry pull/build of base needed.
            for commit,bad in [(b,False),(c,True)]:
                context=root/commit;context.mkdir();dockerfile='FROM saha-release:'+initial+'\nLABEL org.opencontainers.image.revision='+commit+'\n'
                if bad:
                    (context/'main.py').write_text('raise RuntimeError("intentional failed candidate fixture")\n')
                    dockerfile+='COPY main.py /app/backend/app/main.py\n'
                (context/'Dockerfile').write_text(dockerfile)
                run(['docker','build','--pull=false','-t','saha-release:'+commit,str(context)])
                package(commit,root/('bundle-'+commit))
            environment={**os.environ,'SAHA_DEPLOY_HEALTH_ATTEMPTS':'3'}
            updater=['bash',str(ROOT/'scripts/server-update.sh'),'--release','--project',str(project)]
            def bundle_arguments(commit):
                bundle=root/('bundle-'+commit)/'release.tar'
                return ['--bundle',str(bundle),'--commit',commit,'--bundle-bytes',str(bundle.stat().st_size),'--bundle-sha256',digest(bundle)]
            # A truncated wire artifact must fail before any Docker action. The
            # pre-existing app/db containers must keep their original IDs.
            original_ids=subprocess.check_output(compose+['ps','-q','app','db'])
            damaged=root/'truncated.tar';damaged.write_bytes(b'cut off')
            args=bundle_arguments(b);args[1]=str(damaged)
            assert subprocess.run(updater+args,env=environment).returncode!=0
            assert subprocess.check_output(compose+['ps','-q','app','db'])==original_ids
            assert api('/api/v1/health/ready')['database']=='ready'
            assert not (project/'.deploy/state.json').exists()
            assert not (project/'backups').exists()
            run(updater+bundle_arguments(b),env=environment)
            state=json.loads((project/'.deploy/state.json').read_text());assert state['current']['commit']==b
            release_app_id=subprocess.check_output(compose+['ps','-q','app'])
            backup_paths=sorted((project/'backups').glob('*/database.dump'))
            run(updater+bundle_arguments(b),env=environment)
            assert subprocess.check_output(compose+['ps','-q','app'])==release_app_id
            assert sorted((project/'backups').glob('*/database.dump'))==backup_paths
            assert json.loads((project/'.deploy/state.json').read_text())==state
            # Write real durable data AFTER a release, then roll back without restoring its backup.
            day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
            api('/api/v1/admin/scheduling/01',{'services':[{'service_code':'hair-braid','duration_minutes':30}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':720,'step_minutes':30}]},'PUT')
            slot=api('/api/v1/booking/availability?staff_code=01&services=hair-braid&day='+str(day))['slots'][0]
            reservation=api('/api/v1/booking/reservations',{'request_id':str(uuid4()),'customer_name':'Container test fixture','phone':'09123456789','service_codes':['hair-braid'],'staff_code':'01','starts_at':slot['starts_at']},'POST')
            # A real pre-existing JPEG file is uploaded only to the disposable test volume.
            photo=api('/api/v1/admin/gallery-upload',method='POST',binary=(ROOT/'assets/saha-beauty-portrait.jpg').read_bytes(),content_type='image/jpeg')
            api('/api/v1/admin/gallery',{'title':'Container upload fixture','src':photo['src'],'category':'bride','staff_code':'01','is_active':True},'POST')
            image_bytes=api(photo['src'])
            run(['bash',str(ROOT/'scripts/server-update.sh'),'--rollback','--project',str(project),'--rollback-image',state['previous']['image_id']],env=environment)
            assert api('/api/v1/admin/appointments')['items'][0]['id']==reservation['reference']
            assert api(photo['src'])==image_bytes
            failed=subprocess.run(updater+bundle_arguments(c),env=environment)
            assert failed.returncode!=0
            state=json.loads((project/'.deploy/state.json').read_text());assert state['phase']=='rolled_back' and state['current']['commit']==initial
            assert api('/api/v1/admin/appointments')['items'][0]['id']==reservation['reference']
            assert api(photo['src'])==image_bytes
            assert (project/'.env').read_bytes()==original_env
            assert list((project/'backups').glob('*/database.dump'))
            print('Docker/PG: successful release, explicit rollback, failed-health rollback, bookings/uploads/settings preserved')
        finally:
            # These are ONLY the fresh uuid-named integration-test volumes, never production.
            subprocess.run(compose+['down','--volumes','--remove-orphans'],check=False)
if __name__=='__main__':main()
