"""One-time, owner-run Nginx/OTP preparation. Never call the SMS provider or migrate DB."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from .deploy_release import ComposeEngine, DeploymentError, atomic_json, deployment_lock, read_state
except ImportError:
    from deploy_release import ComposeEngine, DeploymentError, atomic_json, deployment_lock, read_state

DOMAIN = 'sahabeauty.ir'
INCLUDE = '/etc/nginx/snippets/saha-release.conf'
SNIPPET = '''# Managed release identity; contains no credentials.
location = /release.json {
    alias /var/lib/saha-release/current/release.json;
    default_type application/json;
    add_header Cache-Control "no-store, max-age=0" always;
}
'''
# Preserve original bytes/offsets, including quotes and comments.
TOKEN = re.compile(r'\#[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{};]|[^\s{};#]+')

def server_blocks(text):
    stack=[];directive=[];servers=[];start=0
    for token in TOKEN.finditer(text):
        value=token.group()
        if value.startswith('#'):continue
        if value=='{':
            kind='server' if directive==['server'] else 'other'
            stack.append({'kind':kind,'open':token.end(),'names':[],'tls':False,'roots':[],'nested_root':False,'header':directive,'proxies':[],'children':[]})
            directive=[]
        elif value=='}':
            if not stack:raise DeploymentError('Unbalanced Nginx configuration; nothing changed')
            block=stack.pop()
            if block['kind']=='server':
                block['end']=token.start();servers.append(block)
            elif stack:stack[-1]['children'].append(block)
            directive=[]
        elif value==';':
            if stack and directive and directive[0]=='proxy_pass':stack[-1]['proxies']+=directive[1:]
            if stack and stack[-1]['kind']=='server' and directive:
                if directive[0]=='server_name':stack[-1]['names']+=directive[1:]
                if directive[0]=='root':stack[-1]['roots'].append((start,token.end(),directive[1:]))
                if directive[0]=='listen' and any(v=='443' or v.endswith(':443') for v in directive[1:]):stack[-1]['tls']=True
            if directive and directive[0]=='root' and stack and stack[-1]['kind']!='server':
                for parent in stack:
                    if parent['kind']=='server':parent['nested_root']=True
            directive=[]
        else:
            if not directive:start=token.start()
            directive.append(value.strip('\"\''))
    if stack:raise DeploymentError('Unbalanced Nginx configuration; nothing changed')
    return servers

def nginx_target(dump):
    sections=re.split(r'^# configuration file (.+):\s*$',dump,flags=re.M)
    found=[]
    for i in range(1,len(sections),2):
        path=Path(sections[i]).resolve()
        text=path.read_text() # The root-owned file, not the decorated nginx -T output.
        for block in server_blocks(text):
            if DOMAIN in block['names'] and block['tls']:found.append((path,text,block))
    unique={(str(p),block['open']):(p,text,block) for p,text,block in found}
    if len(unique)!=1:raise DeploymentError('Cannot uniquely identify the existing HTTPS Nginx vhost; no changes made')
    return next(iter(unique.values()))

def route_site(original,block):
    if block['nested_root'] or len(block['roots'])>1:
        raise DeploymentError('Ambiguous Nginx document root; no configuration changed')
    if block['roots']:
        begin,end,roots=block['roots'][0]
        if len(roots)!=1 or not roots[0].startswith('/') or '$' in roots[0]:
            raise DeploymentError('Existing Nginx document root is ambiguous; no configuration changed')
        return original[:begin]+'root /var/lib/saha-release/current;'+original[end:]
    # A full-site reverse proxy already serves HTML/assets from the running app.
    proxies=[child for child in block['children'] if child['header']==['location','/']]
    if len(proxies)!=1 or len(proxies[0]['proxies'])!=1 or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/?',proxies[0]['proxies'][0]):
        raise DeploymentError('Existing static/proxy routing needs review; no configuration changed')
    return original

def live_environment(environment):
    result=dict(environment)
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',str(result.get('MELIPAYAMAK_API_KEY',''))):
        raise DeploymentError('Existing server OTP API key is missing or invalid; no key generated')
    if len(str(result.get('SAHA_OTP_SECRET','')))<32:
        raise DeploymentError('Existing server OTP signing secret is missing or invalid; no key generated')
    for key in ['SAHA_OTP_ENABLED','SAHA_SMS_LIVE_ENABLED','MELIPAYAMAK_OTP_CONTRACT_CONFIRMED','SAHA_BOOKING_REQUIRE_OTP']:result[key]='1'
    result['SAHA_OTP_TTL_SECONDS']='120'
    # Booking/reminder SMS remains off. No template/key guessing.
    result['SAHA_SMS_NOTIFICATIONS_ENABLED']='0'
    result['SAHA_SMS_TEMPLATES_CONFIRMED']='0'
    return result

def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if result.returncode:raise DeploymentError('Server command failed: '+args[0]+' (exit '+str(result.returncode)+'); private output withheld')
    return result.stdout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0:raise DeploymentError('Run as root in Termius')
    os.umask(0o077)
    project=Path(json.loads(Path('/opt/saha-deploy/config.json').read_text())['project']).resolve()
    command(['nginx','-t'])
    vhost,original,block=nginx_target(command(['nginx','-T']))
    # Existing custom release handlers need review rather than overwriting them.
    if '/release.json' in original and INCLUDE not in original:raise DeploymentError('Existing custom release.json handler needs review; nothing changed')
    proposed=route_site(original,block)
    if INCLUDE not in original:
        offset=block['open'];proposed=proposed[:offset]+'\n    include '+INCLUDE+';\n'+proposed[offset:]
    snippet=Path(INCLUDE)
    if snippet.exists() and snippet.read_text()!=SNIPPET:raise DeploymentError('Existing release snippet differs; nothing changed')
    marker=project/'.deploy/public-release.enabled'
    overlay=project/'.deploy/compose.otp-env.json'
    with deployment_lock(project),tempfile.TemporaryDirectory(dir=project/'.deploy',prefix='prepare-live-') as temporary:
        engine=ComposeEngine(project,Path(temporary))
        state=read_state(project/'.deploy/state.json')
        current=engine.current()
        if state.get('phase')!='healthy' or any(current.get(k)!=state.get('current',{}).get(k) for k in ['image_id','commit']):
            raise DeploymentError('A healthy, recorded current image is required; nothing changed')
        engine.check_schema(current)
        if current['database_revision']!='0005_auth_sms':raise DeploymentError('Reviewed OTP schema must already be installed; no migration performed')
        if not overlay.is_file() or str(overlay) not in engine.files:raise DeploymentError('Existing reviewed OTP environment overlay required')
        data=json.loads(overlay.read_text())
        effective=json.loads(engine.run(engine.compose()+['config','--format','json'],'verify retained Compose settings'))
        resolved=live_environment(effective['services']['app'].get('environment') or {})
        updated=json.loads(json.dumps(data))
        env=updated['services']['app']['environment']
        for key in ['SAHA_OTP_ENABLED','SAHA_SMS_LIVE_ENABLED','MELIPAYAMAK_OTP_CONTRACT_CONFIRMED','SAHA_OTP_TTL_SECONDS','SAHA_SMS_NOTIFICATIONS_ENABLED','SAHA_SMS_TEMPLATES_CONFIRMED','SAHA_BOOKING_REQUIRE_OTP']:
            env[key]=resolved[key]
        if not args.apply:
            print('PREFLIGHT=OK; existing keys valid; no SMS sent; no configuration changed');return
        backup=engine.backup()
        shutil.copy2(vhost,backup/'nginx-vhost.private')
        if snippet.exists():shutil.copy2(snippet,backup/'nginx-snippet.private')
        shutil.copy2(overlay,backup/'otp-overlay.private')
        marker_existed=marker.exists();snippet_existed=snippet.exists()
        stage='publish-current-site'
        try:
            marker.touch(mode=0o600)
            engine.healthy(current) # Publishes the verified current identity, not the desired image.
            snippet.parent.mkdir(parents=True,exist_ok=True)
            snippet.write_text(SNIPPET);snippet.chmod(0o644)
            vhost.write_text(proposed)
            stage='validate-and-reload-nginx'
            command(['nginx','-t']);command(['systemctl','reload','nginx'])
            stage='verify-local-https-route'
            raw=command(['curl','--noproxy','*','--silent','--show-error','--fail','--connect-timeout','3','--max-time','10',
                         '--resolve',DOMAIN+':443:127.0.0.1','https://'+DOMAIN+'/release.json'])
            if json.loads(raw).get('image_id')!=current['image_id']:raise DeploymentError('Local HTTPS release identity does not match; restoring configuration')
            stage='enable-existing-otp-settings'
            atomic_json(overlay,updated)
            engine.switch(current);engine.healthy(current)
            print('PREPARATION=OK; Nginx identity route ready; existing OTP keys retained; real OTP enabled for the next approved app deployment; no SMS sent')
        except BaseException as error:
            reason=str(error) if isinstance(error,DeploymentError) else type(error).__name__
            shutil.copy2(backup/'otp-overlay.private',overlay)
            shutil.copy2(backup/'nginx-vhost.private',vhost)
            if snippet_existed:shutil.copy2(backup/'nginx-snippet.private',snippet)
            else:snippet.unlink(missing_ok=True)
            try:
                engine.switch(current);engine.healthy(current)
                command(['nginx','-t']);command(['systemctl','reload','nginx'])
            except BaseException:raise DeploymentError('Preparation failed and configuration recovery needs attention; live data was not restored or deleted') from None
            if not marker_existed:marker.unlink(missing_ok=True)
            raise DeploymentError('Preparation failed at '+stage+': '+reason+'; previous app/settings restored; no live data restored or deleted') from None

if __name__=='__main__':
    try:main()
    except (DeploymentError,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as error:
        message=str(error) if isinstance(error,DeploymentError) else 'Preparation could not complete; private configuration values withheld'
        raise SystemExit(message) from None
