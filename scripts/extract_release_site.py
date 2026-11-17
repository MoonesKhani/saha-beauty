"""Extract the exact deployed image's site on GitHub instead of bulk SSH download."""
import argparse
import json
from pathlib import Path
import re
import subprocess

try:
    from .image_identity import SavedImageIdentities
except ImportError:
    from image_identity import SavedImageIdentities


def extract(bundle_dir,target,image,commit):
    if not re.fullmatch('sha256:[0-9a-f]{64}',image):raise ValueError('Invalid image identity')
    manifest=json.loads((bundle_dir/'manifest.json').read_text())
    if manifest.get('commit')!=commit:raise ValueError('Site source differs from approved commit')
    retained=[manifest]
    if manifest.get('otp_recovery'):retained.append(manifest['otp_recovery'])
    record=next((r for r in retained if r.get('image_id')==image),None)
    if record is None:raise ValueError('Site image is not in the verified release artifact')
    # The release.tar digest was checked by the workflow. Load only its approved image archive.
    with (bundle_dir/'image.tar.gz').open('rb') as source:
        subprocess.run(['docker','image','load'],stdin=source,check=True,stdout=subprocess.DEVNULL)
    actual=json.loads(subprocess.check_output(['docker','image','inspect',record['image_tag']]))[0]
    runtime=image
    if actual['Id']!=image:runtime=SavedImageIdentities(bundle_dir/'image.tar.gz').verify(record,actual)
    identity=None;target.mkdir(parents=True,exist_ok=False)
    try:
        identity=subprocess.check_output(['docker','create','--pull=never',runtime],text=True).strip()
        subprocess.run(['docker','cp',identity+':/app/frontend/dist/.',str(target)],check=True)
        (target/'release.json').write_text(json.dumps({'image_id':image,'commit':commit})+'\n')
    finally:
        if identity:subprocess.run(['docker','rm',identity],stdout=subprocess.DEVNULL,check=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle-dir',type=Path,required=True);parser.add_argument('--target',type=Path,required=True);parser.add_argument('--image',required=True);parser.add_argument('--commit',required=True)
    args=parser.parse_args();extract(args.bundle_dir,args.target,args.image,args.commit)
