"""Deploy locally loaded images through the existing Compose app. Never restore live data."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from uuid import uuid4

try:
    from .image_identity import SavedImageIdentities,ImageIdentityError
except ImportError:
    from image_identity import SavedImageIdentities,ImageIdentityError

MAX_BUNDLE = 2 * 1024**3
PUBLIC_RELEASE_ROOT = Path('/var/lib/saha-release')
FAILURE_CONTEXT={}


def record_failure(error):
    # Never forward exception strings, stderr, .env values or arbitrary journal lines.
    project=FAILURE_CONTEXT.get('project');commit=FAILURE_CONTEXT.get('commit')
    invocation=os.environ.get('INVOCATION_ID','')
    if not project or not re.fullmatch('[0-9a-f]{40}',commit or '') or not re.fullmatch('[0-9a-f]{32}',invocation):return
    try:
        atomic_json(project/'.deploy/last-failure.json',{'commit':commit,'invocation_id':invocation,
            'stage':FAILURE_CONTEXT.get('stage','preflight'),'operation':error.diagnostic})
    except OSError:pass


SAFE_OPERATIONS=frozenset({
    'load approved image','inspect approved image','verify image identity','inspect current image',
    'verify switched image identity','read schema revision','verify backward-compatible database revision',
    'backup database','backup uploads','verify database backup archive','verify uploads backup archive',
    'seed missing initial records','switch app image','apply reviewed additive OTP migration',
    'inspect offline migration heads','inspect approved migration image','inspect recovery role',
    'verify retained Compose settings','find existing app containers','find existing database',
})
class DeploymentError(RuntimeError):
    def __init__(self,message,*,diagnostic=None):
        super().__init__(message)
        self.diagnostic=diagnostic if diagnostic in SAFE_OPERATIONS else 'deployment safety check'


def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_name(path.name+'.new-'+uuid4().hex)
    try:
        with temporary.open('x') as file:
            os.chmod(temporary,0o600);json.dump(data,file,sort_keys=True);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        while chunk:=file.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()

def verify_bundle_file(bundle,expected_bytes,expected_sha256):
    """Check the complete wire object before opening tar or invoking Docker."""
    if not isinstance(expected_bytes,int) or not 0 < expected_bytes <= MAX_BUNDLE:
        raise DeploymentError('Invalid expected bundle size')
    if not re.fullmatch(r'[0-9a-f]{64}',expected_sha256 or ''):
        raise DeploymentError('Invalid expected bundle SHA-256')
    actual=bundle.stat().st_size
    if actual!=expected_bytes:
        raise DeploymentError(f'Incomplete bundle: expected {expected_bytes} bytes, received {actual}; installation blocked')
    if sha256(bundle)!=expected_sha256:
        raise DeploymentError('Bundle SHA-256 mismatch; installation blocked; re-upload the artifact')

def _unpack_bundle(bundle,stage,expected_commit):
    if not re.fullmatch('[0-9a-f]{40}',expected_commit):raise DeploymentError('Invalid approved commit')
    if bundle.stat().st_size>MAX_BUNDLE:raise DeploymentError('Release bundle too large')
    stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tarfile.open(bundle,'r:') as archive:
        members=archive.getmembers()
        if len(members)!=2 or {m.name for m in members}!={'manifest.json','image.tar.gz'} or any(not m.isfile() for m in members):raise DeploymentError('Unexpected bundle members')
        for member in members:
            if member.size>(65536 if member.name=='manifest.json' else MAX_BUNDLE):raise DeploymentError('Bundle member too large')
            with archive.extractfile(member) as source,(stage/member.name).open('xb') as target:
                os.chmod(target.name,0o600);shutil.copyfileobj(source,target)
    manifest=json.loads((stage/'manifest.json').read_text())
    if not isinstance(manifest,dict):raise DeploymentError('Invalid release manifest; installation blocked')
    if manifest.get('format')!=1 or manifest.get('commit')!=expected_commit or manifest.get('image_tag')!='saha-release:'+expected_commit:raise DeploymentError('Release approval mismatch')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',manifest.get('image_id','')):raise DeploymentError('Invalid image ID')
    if not re.fullmatch(r'[a-zA-Z0-9_]{1,64}',manifest.get('database_revision','')):raise DeploymentError('Invalid database revision')
    image=stage/'image.tar.gz'
    if manifest.get('image_bytes')!=image.stat().st_size or manifest.get('image_sha256')!=sha256(image):raise DeploymentError('Image checksum mismatch')
    return manifest,image


def unpack_bundle(bundle,stage,expected_commit):
    try:
        return _unpack_bundle(bundle,stage,expected_commit)
    except DeploymentError:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    except (tarfile.TarError,EOFError,json.JSONDecodeError,UnicodeDecodeError,TypeError,AttributeError) as error:
        shutil.rmtree(stage,ignore_errors=True)
        raise DeploymentError('Invalid or truncated release archive; installation blocked; re-upload the verified artifact') from error

@contextmanager
def deployment_lock(project):
    directory=project/'.deploy';directory.mkdir(exist_ok=True,mode=0o700)
    with (directory/'deploy.lock').open('a') as file:
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise DeploymentError('Another deployment is running') from None
        yield

def read_state(path):
    return json.loads(path.read_text()) if path.exists() else {}

def apply_release(engine,state_path,candidate,rollback=False):
    """Keep the live DB/uploads on success, failure, manual rollback and retry."""
    state=read_state(state_path)
    if state.get('phase') in ['switching','rollback_failed']:raise DeploymentError('An interrupted switch needs an explicit rollback before another deployment')
    old=engine.current()
    if not rollback and state.get('phase')=='healthy' and state.get('current')==candidate and all(old.get(key)==candidate.get(key) for key in ['image_id','commit']):
        engine.healthy(candidate)
        return state # A retried delivery must not seed/switch/back up an already healthy release.
    if rollback:
        previous=state.get('previous')
        if not previous or previous['image_id']!=candidate['image_id']:raise DeploymentError('Rollback image differs from the approved previous image')
        candidate=previous
    engine.check_schema(old)
    engine.check_schema(candidate) # Pending schema migrations stop BEFORE backup/seed/switch.
    backup=engine.backup()
    journal={**state,'phase':'prepared','current':old,'candidate':candidate,'backup':str(backup)}
    atomic_json(state_path,journal)
    switched=False
    try:
        if not rollback:engine.seed(candidate)
        atomic_json(state_path,{**journal,'phase':'switching'})
        switched=True
        engine.switch(candidate)
        engine.healthy(candidate)
    except BaseException:
        if switched:
            try:
                engine.switch(old);engine.healthy(old)
                atomic_json(state_path,{**state,'phase':'rolled_back','current':old,'failed':candidate,'backup':str(backup)})
            except BaseException:
                atomic_json(state_path,{**journal,'phase':'rollback_failed'})
                raise DeploymentError('Release and image rollback failed; live DB/uploads were NOT restored or deleted') from None
        else:atomic_json(state_path,{**state,'phase':'failed_before_switch','current':old,'failed':candidate,'backup':str(backup)})
        raise DeploymentError('Release failed; previous image retained/restored. Live data was NOT restored from backup') from None
    result={'phase':'healthy','current':candidate,'previous':old,'backup':str(backup),'updated_at':datetime.now(timezone.utc).isoformat()}
    atomic_json(state_path,result)
    return result

def verify_environment(configured,actual,image_defaults):
    actual=dict(item.split('=',1) for item in actual)
    defaults=dict(item.split('=',1) for item in image_defaults)
    for key,value in configured.items():
        expected=None if value is None else str(value)
        if actual.get(key)!=expected:raise DeploymentError('Current container settings differ from Compose/.env; review configuration before deployment')
    # Docker client proxy injection is reused by the same client, not copied to logs/state.
    client_proxy={'HTTP_PROXY','HTTPS_PROXY','NO_PROXY','ALL_PROXY','http_proxy','https_proxy','no_proxy','all_proxy'}
    extras={key for key,value in actual.items() if defaults.get(key)!=value and key not in configured and key not in client_proxy}
    if extras:raise DeploymentError('Container has settings outside the retained Compose files; declare them before deployment')

SCHEMA_CODE = '''
import json
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from backend.app.config import Settings
from backend.app.db import make_engine
engine=make_engine(Settings().database_url)
with engine.connect() as connection: actual=list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
heads=ScriptDirectory.from_config(Config('database/alembic.ini')).get_heads()
engine.dispose()
if len(heads)!=1 or actual!=heads: raise SystemExit('Schema migration requires a separate reviewed maintenance plan')
print(json.dumps({'revision':heads[0]}))
'''

class ComposeEngine:
    def __init__(self,project,stage):
        self.project=project.resolve();self.stage=stage;self.resolved_images=[]
        if not (self.project/'compose.yaml').is_file() or not (self.project/'.env').is_file():raise DeploymentError('Existing Compose deployment and .env required')
        self.managed=self.project/'.deploy/compose.release.json'
        identities=self.run(['docker','ps','--all','--filter','label=com.docker.compose.service=app','--format','{{.ID}}'],'find existing app containers').splitlines()
        matches=[]
        for identity in identities:
            candidate=self.inspect(identity);labels=candidate.get('Config',{}).get('Labels') or {}
            if labels.get('com.docker.compose.oneoff')!='True' and Path(labels.get('com.docker.compose.project.working_dir','/')).resolve()==self.project:matches.append(candidate)
        if len(matches)!=1:raise DeploymentError('Exactly one existing app for this project directory is required')
        info=matches[0]
        self.project_name=info['Config']['Labels']['com.docker.compose.project']
        initial=['docker','compose','--project-directory',str(self.project),'--project-name',self.project_name,'-f',str(self.project/'compose.yaml')]
        db=self.run(initial+['ps','-q','db'],'find existing database').strip()
        if not db:raise DeploymentError('The existing database must be running')
        files=info['Config']['Labels'].get('com.docker.compose.project.config_files','').split(',')
        self.files=[str(Path(f).resolve()) for f in files if f and Path(f).resolve()!=self.managed]
        if not self.files or any(not Path(f).is_file() for f in self.files):raise DeploymentError('Original Compose files are unavailable; stop rather than replace configuration')
        ports=info.get('NetworkSettings',{}).get('Ports',{}).get('8000/tcp') or info.get('HostConfig',{}).get('PortBindings',{}).get('8000/tcp') or []
        if len(ports)!=1:raise DeploymentError('Existing app port cannot be determined')
        self.base_url='http://127.0.0.1:'+ports[0]['HostPort']
        self.mounts=self.mount_signature(info)
        if not any(m[2]=='/app/var' and m[0]=='volume' for m in self.mounts):raise DeploymentError('Existing persistent uploads volume is required')
        self.initial=info
        effective=json.loads(self.run(self.compose()+['config','--format','json'],'verify retained Compose settings'))
        for service,container in [('app',info),('db',self.inspect(db))]:
            image=json.loads(self.run(['docker','image','inspect',container['Image']],'inspect original image defaults'))[0]
            self.verify_container_environment(service,effective['services'][service].get('environment') or {},container['Config'].get('Env') or [],image.get('Config',{}).get('Env') or [])

    def verify_container_environment(self,service,configured,actual,image_defaults):
        # Ordinary release/rollback always retains the complete strict check.
        verify_environment(configured,actual,image_defaults)

    def run(self,args,label,stdin=None,stdout=None):
        result=subprocess.run(args,cwd=self.project,stdin=stdin,stdout=stdout or subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:raise DeploymentError(label+' failed; inspect local service logs (credentials are not printed here)',diagnostic=label)
        return result.stdout.decode().strip() if stdout is None else ''

    def inspect(self,identity):return json.loads(self.run(['docker','inspect',identity],'inspect Docker object'))[0]

    @staticmethod
    def mount_signature(info):return sorted((m['Type'],m.get('Name',m.get('Source','')),m['Destination'],m.get('RW',True)) for m in info['Mounts'])

    def compose(self,overlay=None):
        args=['docker','compose','--project-directory',str(self.project),'--project-name',self.project_name]
        for file in self.files:args+=['-f',file]
        if overlay:args+=['-f',str(overlay)]
        elif self.managed.exists():args+=['-f',str(self.managed)]
        return args

    def overlay(self,record,path):
        atomic_json(path,{'services':{'app':{'image':self.image_reference(record),'pull_policy':'never','command':['python','-m','uvicorn','backend.app.main:app','--host','0.0.0.0','--port','8000','--proxy-headers','--forwarded-allow-ips=*']}}})
        return path

    @staticmethod
    def image_reference(record):
        identity=record.get('runtime_image_id') or record['image_id']
        if not isinstance(identity,str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',identity):raise DeploymentError('Invalid retained runtime image identity')
        return identity

    def current(self):
        identity=self.run(self.compose()+['ps','-q','app'],'find current app')
        info=self.inspect(identity)
        if info['State']['Status']!='running':raise DeploymentError('Current app is not running')
        image_info=json.loads(self.run(['docker','image','inspect',info['Image']],'inspect current image'))[0]
        runtime=image_info['Id'];commit=(image_info.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')
        state=read_state(self.project/'.deploy/state.json')
        records=[state.get(key) or {} for key in ['current','previous','recovery','legacy_original']]+self.resolved_images
        known=next((r for r in records if r.get('commit')==commit and (r.get('runtime_image_id') or r.get('image_id'))==runtime),None)
        image=known['image_id'] if known else runtime
        self.run(['docker','image','tag',runtime,'saha-retained:'+image.split(':')[1]],'retain rollback image')
        result={'image_id':image,'commit':commit}
        if runtime!=image:result['runtime_image_id']=runtime
        return result

    def check_schema(self,record):
        overlay=self.overlay(record,self.stage/('probe-'+record['image_id'].split(':')[1]+'.json'))
        data=json.loads(self.run(self.compose(overlay)+['run','--rm','--no-deps','--pull','never','--entrypoint','python','app','-c',SCHEMA_CODE],'verify backward-compatible database revision'))
        if record.get('database_revision') and record['database_revision']!=data['revision']:raise DeploymentError('Manifest database revision mismatch')
        record['database_revision']=data['revision']

    def backup(self):
        database_bytes=int(self.run(self.compose()+['exec','-T','db','psql','-U','saha','-d','saha','-Atqc','SELECT pg_database_size(current_database())'],'estimate database backup size'))
        upload_kib=int(self.run(self.compose()+['exec','-T','app','du','-sk','/app/var'],'estimate uploads backup size').split()[0])
        if shutil.disk_usage(self.project).free<database_bytes*2+upload_kib*2048+1024**3:raise DeploymentError('Insufficient free disk for safe backups')
        name='release-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]
        directory=self.project/'backups'/name;directory.mkdir(parents=True,mode=0o700)
        with (directory/'database.dump').open('xb') as output:self.run(self.compose()+['exec','-T','db','pg_dump','-U','saha','-d','saha','-Fc'],'backup database',stdout=output)
        with (directory/'uploads.tar.gz').open('xb') as output:self.run(self.compose()+['exec','-T','app','tar','-C','/app/var','-czf','-','.'],'backup uploads',stdout=output)
        for filename in ['database.dump','uploads.tar.gz']:
            if not (directory/filename).stat().st_size:raise DeploymentError('Empty backup; deployment stopped')
        with (directory/'database.dump').open('rb') as source:self.run(self.compose()+['exec','-T','db','pg_restore','--list'],'verify database backup archive',stdin=source)
        self.run(['tar','-tzf',str(directory/'uploads.tar.gz')],'verify uploads backup archive')
        shutil.copyfile(self.project/'.env',directory/'environment.private')
        for index,file in enumerate(self.files):shutil.copyfile(file,directory/f'compose-{index}.private')
        atomic_json(directory/'checksums.json',{p.name:sha256(p) for p in directory.iterdir() if p.is_file()})
        return directory

    def seed(self,record):
        overlay=self.overlay(record,self.stage/'seed.json')
        self.run(self.compose(overlay)+['run','--rm','--no-deps','--pull','never','--entrypoint','python','app','-m','backend.app.cli','seed'],'seed missing initial records')

    def switch(self,record):
        self.overlay(record,self.managed)
        self.run(self.compose()+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','app'],'switch app image')
        info=self.inspect(self.run(self.compose()+['ps','-q','app'],'find switched app'))
        actual=json.loads(self.run(['docker','image','inspect',info['Image']],'verify switched image identity'))[0]
        if actual['Id']!=self.image_reference(record) or self.mount_signature(info)!=self.mounts:raise DeploymentError('Image or persistent mounts differ from the approved deployment')

    def healthy(self,record):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last=None
        for _ in range(max(1,min(90,int(os.environ.get('SAHA_DEPLOY_HEALTH_ATTEMPTS','30'))))):
            try:
                with opener.open(self.base_url+'/api/v1/health/ready',timeout=3) as response:
                    readiness=json.load(response)
                    if readiness.get('status')!='ok' or readiness.get('database')!='ready':raise DeploymentError('Readiness response mismatch')
                for path,field in [('/api/v1/catalog','services'),('/api/v1/packages','items'),('/api/v1/booking/catalog','team')]:
                    with opener.open(self.base_url+path,timeout=3) as response:
                        if not isinstance(json.load(response).get(field),list):raise DeploymentError('Functional check failed')
                self.publish_identity(record)
                return
            except Exception as error:last=error;time.sleep(2)
        raise DeploymentError('Application readiness/functional checks failed') from last

    def publish_identity(self,record):
        # Opt-in host Nginx endpoint. Publish only after health and actual image checks;
        # rollback uses the same path, so the public identity follows the running app.
        if not (self.project/'.deploy/public-release.enabled').is_file():return
        info=self.inspect(self.run(self.compose()+['ps','-q','app'],'find current app'))
        actual=json.loads(self.run(['docker','image','inspect',info['Image']],'inspect current image'))[0]
        if actual['Id']!=self.image_reference(record):raise DeploymentError('Public release identity differs from running image')
        if (actual.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')!=record.get('commit'):
            raise DeploymentError('Public release revision differs from running image')
        target=PUBLIC_RELEASE_ROOT
        target.mkdir(mode=0o755,parents=True,exist_ok=True)
        os.chmod(target,0o755)
        # Nginx serves the static files and identity from ONE atomic directory
        # switch. A standalone identity file must never mask stale HTML/assets.
        sites=target/'sites';sites.mkdir(mode=0o755,exist_ok=True)
        release=sites/record['image_id'].split(':')[1]
        if not release.exists():
            with tempfile.TemporaryDirectory(prefix='site-',dir=sites) as temporary:
                stage=Path(temporary)/'public';stage.mkdir(mode=0o755)
                self.run(['docker','cp',info['Id']+':/app/frontend/dist/.',str(stage)],'extract verified public site')
                if not (stage/'index.html').is_file():raise DeploymentError('Approved static site is missing')
                size=0
                for item in stage.rglob('*'):
                    if item.is_symlink() or not (item.is_file() or item.is_dir()):raise DeploymentError('Unsafe static site entry')
                    if item.is_file():size+=item.stat().st_size
                    item.chmod(0o755 if item.is_dir() else 0o644)
                if size>100*1024**2:raise DeploymentError('Approved static site exceeds size limit')
                atomic_json(stage/'release.json',{key:record[key] for key in ['image_id','commit']})
                (stage/'release.json').chmod(0o644)
                os.replace(stage,release)
        wanted={key:record[key] for key in ['image_id','commit']}
        if json.loads((release/'release.json').read_text())!=wanted:raise DeploymentError('Retained static site identity mismatch')
        link=target/('current.new-'+uuid4().hex)
        try:
            link.symlink_to(release,target_is_directory=True)
            os.replace(link,target/'current')
        finally:link.unlink(missing_ok=True)

    def load(self,manifest,image):
        proof=None
        records=[manifest]
        if manifest.get('otp_recovery'):records.append(manifest['otp_recovery'])
        for record in records:record.pop('runtime_image_id',None)
        def verify_loaded():
            nonlocal proof
            resolved=[]
            for record in records:
                info=json.loads(self.run(['docker','image','inspect',record['image_tag']],'inspect approved image'))[0]
                if (info.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')!=record['commit']:
                    raise DeploymentError('Loaded image revision mismatch',diagnostic='verify image identity')
                runtime=None
                if info['Id']!=record['image_id']:
                    try:
                        if proof is None:proof=SavedImageIdentities(image)
                        runtime=proof.verify(record,info)
                    except ImageIdentityError as error:raise DeploymentError('Image identity proof failed: '+str(error),diagnostic='verify image identity') from None
                resolved.append((record,runtime))
            for record,runtime in resolved:
                if runtime:record['runtime_image_id']=runtime
        try:
            verify_loaded() # Reuse only images proven to be the exact approved content.
        except DeploymentError:
            if shutil.disk_usage(self.project).free<max(4*1024**3,image.stat().st_size*4):raise DeploymentError('Insufficient free disk for image and rollback')
            with image.open('rb') as source:self.run(['docker','image','load'],'load approved image',stdin=source)
            verify_loaded()
        self.resolved_images.extend(dict(record) for record in records)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--bundle',type=Path);parser.add_argument('--commit');parser.add_argument('--bundle-bytes',type=int);parser.add_argument('--bundle-sha256');parser.add_argument('--rollback-image');parser.add_argument('--status',action='store_true')
    args=parser.parse_args();project=args.project.resolve();os.umask(0o077)
    if not project.is_dir():raise DeploymentError('Project directory not found')
    state_path=project/'.deploy/state.json'
    if args.status:print(json.dumps(read_state(state_path),sort_keys=True));return
    FAILURE_CONTEXT.update(project=project,commit=args.commit,stage='read-approved-bundle')
    with deployment_lock(project),tempfile.TemporaryDirectory(prefix='release-',dir=project/'.deploy') as temporary:
        stage=Path(temporary)
        if not args.rollback_image:
            if not args.bundle or not args.commit or args.bundle_bytes is None or not args.bundle_sha256:
                raise DeploymentError('Approved commit, expected bundle bytes and SHA-256 are required; installation blocked')
            verify_bundle_file(args.bundle.resolve(),args.bundle_bytes,args.bundle_sha256)
            manifest,image=unpack_bundle(args.bundle.resolve(),stage/'bundle',args.commit)
        FAILURE_CONTEXT['stage']='inspect-existing-configuration'
        engine=ComposeEngine(project,stage)
        if args.rollback_image:
            if not re.fullmatch(r'sha256:[0-9a-f]{64}',args.rollback_image):raise DeploymentError('Invalid approved rollback image')
            state=read_state(state_path)
            if state.get('phase') in ['switching','rollback_failed']:
                # Recovery after a lost connection/process uses the last known good image.
                previous=state.get('current')
                if not previous or previous['image_id']!=args.rollback_image:raise DeploymentError('Recovery approval mismatch')
                engine.check_schema(previous);engine.switch(previous);engine.healthy(previous)
                atomic_json(state_path,{**state,'phase':'healthy','current':previous,'previous':previous,'recovered_from':state.get('candidate')})
                print(json.dumps(read_state(state_path),sort_keys=True));return
            result=apply_release(engine,state_path,{'image_id':args.rollback_image},rollback=True)
        else:
            FAILURE_CONTEXT['stage']='load-approved-images'
            engine.load(manifest,image)
            candidate={k:manifest[k] for k in ['image_id','commit','database_revision']}
            if manifest.get('runtime_image_id'):candidate['runtime_image_id']=manifest['runtime_image_id']
            FAILURE_CONTEXT['stage']='apply-approved-release'
            result=apply_release(engine,state_path,candidate)
        print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
    def interrupted(signum,frame):raise DeploymentError('Deployment interrupted; attempting image recovery if a switch began')
    for signum in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(signum,interrupted)
    try:main()
    except DeploymentError as error:
        record_failure(error)
        raise SystemExit(str(error)) from None
    except OSError as error:
        record_failure(DeploymentError('I/O error'))
        raise SystemExit(f'Release I/O error (errno {error.errno}); read deployment status before retry') from None
