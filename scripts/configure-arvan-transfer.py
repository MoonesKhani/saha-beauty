"""Root-only destination pinning; no credentials, service restart or app/env changes."""
import argparse
import os
from pathlib import Path
try:
    from .artifact_fetch import storage_policy
    from .deploy_release import atomic_json
except ImportError:
    from artifact_fetch import storage_policy
    from deploy_release import atomic_json

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--endpoint',required=True);parser.add_argument('--bucket',required=True);parser.add_argument('--region',required=True);parser.add_argument('--prefix',default='saha-releases/')
    args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run in Termius as root; no change made')
    root=Path('/opt/saha-deploy')
    if not (root/'config.json').is_file():raise SystemExit('Existing restricted deployment installation required')
    try:config=storage_policy(vars(args))
    except ValueError:raise SystemExit('Invalid destination; use the exact private Arvan bucket endpoint/region') from None
    path=root/'arvan-transfer.json';os.umask(0o077)
    if path.exists() and path.read_text().strip():
        import shutil,tempfile
        with tempfile.NamedTemporaryFile(prefix='arvan-policy-backup-',dir=root,delete=False) as backup:
            with path.open('rb') as source:shutil.copyfileobj(source,backup)
    atomic_json(path,config)
    print('Exact Arvan release destination saved. No credentials stored; app, database, uploads and .env unchanged.')
