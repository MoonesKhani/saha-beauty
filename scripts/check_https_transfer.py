"""Small artifact probe only. No deployment or application image can be installed."""
import argparse
import json
import os
from pathlib import Path
import time
try:
    from .transfer_release import Sender,TransferError
    from .https_release import stage,DownloadError
except ImportError:
    from transfer_release import Sender,TransferError
    from https_release import stage,DownloadError

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('ssh',nargs=argparse.REMAINDER)
    args=parser.parse_args();ssh=args.ssh[1:] if args.ssh[:1]==['--'] else args.ssh
    if args.bundle.stat().st_size>256*1024:raise SystemExit('Diagnostic sample is too large')
    sender=Sender(ssh,args.bundle,os.environ['GITHUB_SHA'],Path(os.environ['RUNNER_TEMP'])/'unused-diagnostic-report',expected_image='sha256:'+'0'*64)
    name='saha-https-probe-'+os.environ['GITHUB_RUN_ID']
    try:
        result=stage(sender,os.environ['GITHUB_RUN_ID'],name,probe=True)
        print(json.dumps(result,sort_keys=True),flush=True)
        start=time.monotonic()
        verified=stage(sender,os.environ['GITHUB_RUN_ID'],name,check=True)
        print(json.dumps({'verified_small_zip':verified['complete'],'seconds':round(time.monotonic()-start,3),'installation_requested':False},sort_keys=True))
    except (TransferError,DownloadError) as error:raise SystemExit(str(error)) from None
