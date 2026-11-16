"""Reject PR artifacts, failed runs, other repositories and mismatched approvals."""
import argparse,json,re,subprocess

def validate(run,repository,commit,confirmation,operation="deploy"):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Use the full approved commit SHA')
    if operation not in ('deploy','otp-migration'):raise ValueError('Invalid operation')
    if confirmation!=('MIGRATE OTP ' if operation=='otp-migration' else 'DEPLOY ')+commit:raise ValueError('Explicit DEPLOY confirmation for this commit is required')
    if run.get('repository',{}).get('full_name')!=repository:raise ValueError('Wrong repository')
    if run.get('head_repository',{}).get('full_name')!=repository:raise ValueError('Fork artifacts are not deployable')
    if run.get('head_sha')!=commit or run.get('head_branch')!='main':raise ValueError('Only the approved main commit is deployable')
    if run.get('event') not in ['push','workflow_dispatch']:raise ValueError('PR artifacts are not deployable')
    if run.get('status')!='completed' or run.get('conclusion')!='success':raise ValueError('CI must complete successfully')
    if run.get('path')!='.github/workflows/ci.yml':raise ValueError('Unexpected build workflow')

def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',required=True);p.add_argument('--run-id',required=True);p.add_argument('--commit',required=True);p.add_argument('--confirmation',required=True)
    p.add_argument('--operation',choices=['deploy','otp-migration'],default='deploy')
    a=p.parse_args()
    if not re.fullmatch('[0-9]+',a.run_id):raise ValueError('Invalid CI run ID')
    run=json.loads(subprocess.check_output(['gh','api',f'repos/{a.repository}/actions/runs/{a.run_id}']))
    validate(run,a.repository,a.commit,a.confirmation,a.operation)
    subprocess.run(['git','merge-base','--is-ancestor',a.commit,'origin/main'],check=True)
    print('Approved main release and successful CI verified')
if __name__=='__main__':main()
