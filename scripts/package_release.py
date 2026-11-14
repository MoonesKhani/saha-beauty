"""Create a self-contained image bundle on CI; no registry is needed by production."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

SCHEMA_CODE = "from alembic.config import Config; from alembic.script import ScriptDirectory; import json; print(json.dumps(ScriptDirectory.from_config(Config('database/alembic.ini')).get_heads()))"

def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file,'sha256').hexdigest()

def package(commit, output):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('A full commit SHA is required')
    output.mkdir(parents=True,exist_ok=True)
    tag='saha-release:'+commit
    info=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
    if info.get('Config',{}).get('Labels',{}).get('org.opencontainers.image.revision')!=commit:raise ValueError('Image revision label mismatch')
    heads=json.loads(subprocess.check_output(['docker','run','--rm','--pull=never','--network=none','--entrypoint','python',tag,'-c',SCHEMA_CODE]))
    if len(heads)!=1:raise ValueError('Exactly one database revision is required')
    image=output/'image.tar.gz'
    with image.open('wb') as target:
        with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0) as zipped:
            process=subprocess.Popen(['docker','image','save',tag],stdout=subprocess.PIPE)
            try:
                while chunk:=process.stdout.read(1024*1024):zipped.write(chunk)
            finally:process.stdout.close()
            if process.wait()!=0:raise RuntimeError('docker save failed')
    manifest={'format':1,'commit':commit,'image_id':info['Id'],'image_tag':tag,'image_sha256':digest(image),'image_bytes':image.stat().st_size,'database_revision':heads[0]}
    (output/'manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
    bundle=output/'release.tar'
    with tarfile.open(bundle,'w') as archive:
        for name in ['manifest.json','image.tar.gz']:archive.add(output/name,arcname=name)
    (output/'release.tar.sha256').write_text(digest(bundle)+'  release.tar\n')
    print(json.dumps({'commit':commit,'bundle_sha256':digest(bundle),'database_revision':heads[0]}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--commit',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();package(args.commit,args.output)
