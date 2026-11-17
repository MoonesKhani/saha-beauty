"""Explicit one-time 0004→0005 maintenance. No ordinary release-guard exception."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

try:
    from .deploy_release import ComposeEngine,DeploymentError,atomic_json,read_state,deployment_lock,verify_bundle_file,unpack_bundle,apply_release,FAILURE_CONTEXT,record_failure
except ImportError:
    from deploy_release import ComposeEngine,DeploymentError,atomic_json,read_state,deployment_lock,verify_bundle_file,unpack_bundle,apply_release,FAILURE_CONTEXT,record_failure

LEGACY='cddc860800bf654af5f4483c32f8de646a598536'
OLD='0004_packages';NEW='0005_auth_sms'
HEADS="from alembic.config import Config; from alembic.script import ScriptDirectory; import json; print(json.dumps(ScriptDirectory.from_config(Config('database/alembic.ini')).get_heads()))"
ENVIRONMENT={
 'MELIPAYAMAK_API_KEY':'${MELIPAYAMAK_API_KEY:-}', 'SAHA_OTP_SECRET':'${SAHA_OTP_SECRET:-}',
 'MELIPAYAMAK_OTP_CONTRACT_CONFIRMED':'${MELIPAYAMAK_OTP_CONTRACT_CONFIRMED:-0}',
 'SAHA_OTP_TTL_SECONDS':'${SAHA_OTP_TTL_SECONDS:-120}',
 'MELIPAYAMAK_BOOKING_BODY_ID':'${MELIPAYAMAK_BOOKING_BODY_ID:-0}',
 'MELIPAYAMAK_REPAIR_BODY_ID':'${MELIPAYAMAK_REPAIR_BODY_ID:-0}',
 'SAHA_OTP_ENABLED':'0','SAHA_SMS_LIVE_ENABLED':'0','SAHA_SMS_NOTIFICATIONS_ENABLED':'0',
 'SAHA_SMS_TEMPLATES_CONFIRMED':'0','SAHA_BOOKING_REQUIRE_OTP':'0',
}


def validate_recovery(manifest):
    if manifest.get('database_revision')!=NEW:raise DeploymentError('Only the reviewed OTP migration is supported')
    recovery=manifest.get('otp_recovery') or {}
    if (recovery.get('commit')!=manifest.get('commit') or recovery.get('database_revision')!=NEW
        or recovery.get('legacy_commit')!=LEGACY or not re.fullmatch('sha256:[0-9a-f]{64}',recovery.get('image_id',''))):
        raise DeploymentError('A reviewed schema-compatible recovery image is required')
    return recovery


def maintain(engine,state_path,primary,recovery):
    state=read_state(state_path)
    if state.get('phase') in ('switching','rollback_failed'):raise DeploymentError('Unresolved previous transaction; inspect status first')
    revision=engine.database_revision()
    if revision==NEW:
        if state.get('otp_migration_commit')!=primary['commit']:
            raise DeploymentError('Database is already 0005 outside this recorded maintenance; read status before proceeding')
        result=apply_release(engine,state_path,primary)
        result.update(otp_migration_commit=primary['commit'],legacy_original=state.get('legacy_original'),recovery=recovery)
        atomic_json(state_path,result)
        return result
    if revision!=OLD:raise DeploymentError('Unexpected database revision; nothing migrated')
    old=engine.current()
    if old['image_id']!=recovery['image_id']:engine.check_schema(old)
    legacy=state.get('legacy_original') or old
    backup=engine.backup() # Must complete before environment overlays or image changes.
    journal={**state,'phase':'otp_backup_ready','current':old,'previous':old,'legacy_original':legacy,
        'otp_migration_commit':primary['commit'],'recovery':recovery,'backup':str(backup)}
    atomic_json(state_path,journal)
    try:
        engine.quiet_environment()
        engine.switch(recovery);engine.healthy(recovery)
        atomic_json(state_path,{**journal,'phase':'otp_bridge_running','current':recovery})
        engine.migrate(recovery)
        if engine.database_revision()!=NEW:raise DeploymentError('OTP schema transition was not confirmed')
        engine.check_schema(recovery);engine.healthy(recovery)
        atomic_json(state_path,{**journal,'phase':'healthy','current':recovery,'previous':recovery})
        # Ordinary safety checks now apply unchanged: old, new and live DB are all 0005.
        result=apply_release(engine,state_path,primary)
        result.update(otp_migration_commit=primary['commit'],legacy_original=legacy,recovery=recovery)
        atomic_json(state_path,result)
        return result
    except BaseException:
        try:
            revision=engine.database_revision()
            if revision not in (OLD,NEW):raise DeploymentError('Unknown schema after maintenance interruption')
            fallback=recovery if revision==NEW else legacy
            engine.switch(fallback);engine.healthy(fallback)
            atomic_json(state_path,{**journal,'phase':'otp_maintenance_stopped','current':fallback,'previous':fallback,'database_revision':revision})
        except BaseException:
            atomic_json(state_path,{**journal,'phase':'rollback_failed'})
            raise DeploymentError('OTP maintenance and compatible image recovery failed; live data was NOT restored or deleted') from None
        raise DeploymentError('OTP maintenance stopped; compatible image retained/restored; no live data restore performed') from None

class MaintenanceEngine(ComposeEngine):
    def verify_container_environment(self,service,configured,actual,image_defaults):
        if service!='app':
            return super().verify_container_environment(service,configured,actual,image_defaults)
        present={item.split('=',1)[0] for item in actual}
        defaults={item.split('=',1)[0] for item in image_defaults}
        additions={key for key in configured if key in ENVIRONMENT and key not in present and key not in defaults}
        for key in additions:
            if ENVIRONMENT[key]=='0' and str(configured[key])!='0':
                raise DeploymentError('New OTP/SMS and booking-proof flags must remain disabled during maintenance')
        # Only the reviewed additions can differ BEFORE backup. Existing keys,
        # unknown additions, the database and all normal releases stay strict.
        retained={key:value for key,value in configured.items() if key not in additions}
        super().verify_container_environment(service,retained,actual,image_defaults)

    def database_revision(self):
        return self.run(self.compose()+['exec','-T','db','psql','-U','saha','-d','saha','-Atqc','SELECT version_num FROM alembic_version'],'read schema revision')
    def quiet_environment(self):
        path=self.project/'.deploy/compose.otp-env.json'
        atomic_json(path,{'services':{'app':{'environment':ENVIRONMENT}}})
        if str(path) not in self.files:self.files.append(str(path))
    def migrate(self,recovery):
        overlay=self.overlay(recovery,self.stage/'otp-migration.json')
        self.run(self.compose(overlay)+['run','--rm','--no-deps','--pull','never','--entrypoint','python','app','-m','backend.app.cli','migrate'],'apply reviewed additive OTP migration')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--commit',required=True);parser.add_argument('--bundle-sha256',required=True);parser.add_argument('--bundle-bytes',type=int,required=True);parser.add_argument('--apply',action='store_true');parser.add_argument('--confirmation',default='')
    args=parser.parse_args();os.umask(0o077)
    if args.apply and args.confirmation!='MIGRATE OTP '+args.commit:raise DeploymentError('Exact separate OTP maintenance approval required')
    verify_bundle_file(args.bundle,args.bundle_bytes,args.bundle_sha256)
    project=args.project.resolve()
    if not project.is_dir():raise DeploymentError('Existing project required')
    FAILURE_CONTEXT.update(project=project,commit=args.commit,stage='read-approved-bundle')
    with deployment_lock(project),tempfile.TemporaryDirectory(prefix='otp-maintenance-',dir=project/'.deploy') as temporary:
        stage=Path(temporary);manifest,image=unpack_bundle(args.bundle,stage/'bundle',args.commit)
        recovery=validate_recovery(manifest);primary={key:manifest[key] for key in ['commit','image_id','database_revision']}
        FAILURE_CONTEXT['stage']='inspect-existing-configuration'
        engine=MaintenanceEngine(project,stage)
        if not args.apply:
            print(json.dumps({'mode':'plan','source':args.commit,'current_schema':engine.database_revision(),'target_schema':NEW,'recovery_image':recovery['image_id'],'sms_enabled':False}));return
        FAILURE_CONTEXT['stage']='load-approved-images'
        engine.load(manifest,image)
        if manifest.get('runtime_image_id'):primary['runtime_image_id']=manifest['runtime_image_id']
        FAILURE_CONTEXT['stage']='verify-image-schema'
        for record in (primary,recovery):
            info=json.loads(engine.run(['docker','image','inspect',engine.image_reference(record)],'inspect approved migration image'))[0]
            labels=info.get('Config',{}).get('Labels') or {}
            if labels.get('org.opencontainers.image.revision')!=args.commit:raise DeploymentError('Migration image label mismatch')
            heads=json.loads(engine.run(['docker','run','--rm','--pull=never','--network=none','--entrypoint','python',engine.image_reference(record),'-c',HEADS],'inspect offline migration heads'))
            if heads!=[NEW]:raise DeploymentError('Migration image schema mismatch')
        rec_info=json.loads(engine.run(['docker','image','inspect',engine.image_reference(recovery)],'inspect recovery role'))[0]
        if rec_info['Config']['Labels'].get('saha.otp-recovery')!='true' or rec_info['Config']['Labels'].get('saha.legacy-source')!=LEGACY:raise DeploymentError('Recovery role mismatch')
        FAILURE_CONTEXT['stage']='reviewed-otp-maintenance'
        result=maintain(engine,project/'.deploy/state.json',primary,recovery)
        print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    import signal
    def interrupted(signum,frame):raise DeploymentError('Maintenance interrupted; attempting compatible image recovery')
    for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(signum,interrupted)
    try:main()
    except DeploymentError as error:
        record_failure(error)
        raise SystemExit(str(error)) from None
    except OSError:
        record_failure(DeploymentError('I/O error'))
        raise SystemExit('OTP maintenance I/O error; read status before retry') from None
