"""Build a small schema-compatible recovery layer on CI, never on the live server."""
import argparse
from io import BytesIO
from pathlib import Path,PurePosixPath
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
LEGACY='cddc860800bf654af5f4483c32f8de646a598536'


def allowed(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:return False
    return ((name.startswith('backend/app/') and name.endswith('.py')) or
        name.startswith('database/') or name in ['frontend/build.py','frontend/src/admin.html','frontend/src/leisure.html'] or
        (len(path.parts)==1 and name.endswith('.html')) or
        (name.startswith('assets/') and name.endswith(('.js','.css'))))


def legacy_files():
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',LEGACY],cwd=ROOT,text=True).splitlines()
    names=[name for name in names if allowed(name)]
    data=subprocess.check_output(['git','archive',LEGACY,'--',*names],cwd=ROOT)
    with tarfile.open(fileobj=BytesIO(data)) as archive:
        return {item.name:archive.extractfile(item).read() for item in archive.getmembers() if item.isfile()}


def context(output,commit,files=None):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Exact release SHA required')
    files=dict(legacy_files() if files is None else files)
    if any(not allowed(name) for name in files):raise ValueError('Only tracked recovery source files are allowed')
    main=files['backend/app/main.py'].decode()
    marker="if version != '0004_packages':"
    if main.count(marker)!=1:raise ValueError('Pinned legacy readiness differs; review recovery source')
    files['backend/app/main.py']=main.replace(marker,"if version not in ('0004_packages','0005_auth_sms'):").encode()
    settings=files['backend/app/config.py'].decode()
    marker="os.environ.get('SAHA_BOOKING_ENABLED', '0') == '1'"
    if settings.count(marker)!=1:raise ValueError('Pinned booking gate differs; review recovery source')
    # Once phone proof is required, a legacy fallback must not allow anonymous bookings.
    files['backend/app/config.py']=settings.replace(marker,"("+marker+" and os.environ.get('SAHA_BOOKING_REQUIRE_OTP','0') != '1')").encode()
    files['database/migrations/versions/0005_auth_sms.py']=(ROOT/'database/migrations/versions/0005_auth_sms.py').read_bytes()
    output.mkdir(parents=True,exist_ok=True)
    for name,data in files.items():
        path=output/'overlay'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    dockerfile=f'''FROM saha-release:{commit}
USER root
RUN rm -rf /app/backend/app /app/database /app/frontend/dist
COPY --chown=saha:saha overlay/ /app/
RUN python /app/frontend/build.py
LABEL org.opencontainers.image.revision="{commit}" saha.otp-recovery="true" saha.legacy-source="{LEGACY}"
USER saha
'''
    (output/'Dockerfile').write_text(dockerfile)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--commit',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--build',action='store_true')
    args=parser.parse_args();context(args.output,args.commit)
    if args.build:subprocess.run(['docker','build','--pull=false','--network=none','-t','saha-otp-recovery:'+args.commit,str(args.output)],check=True)
