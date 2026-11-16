#!/usr/bin/env python3
"""Run one outbox job inside the existing app; no build/pull/migration or secret output."""
import json
from pathlib import Path
import subprocess


def choose_app(records, project):
    matches=[row['Id'] for row in records
        if row.get('State',{}).get('Running')
        and row.get('Config',{}).get('Labels',{}).get('com.docker.compose.oneoff')!='True'
        and Path(row.get('Config',{}).get('Labels',{}).get('com.docker.compose.project.working_dir','/')).resolve()==project]
    if len(matches)!=1:raise ValueError('Exactly one existing app container is required')
    return matches[0]


def main():
    config=json.loads(Path('/opt/saha-deploy/config.json').read_text())
    project=Path(config['project']).resolve()
    identities=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.service=app','--format','{{.ID}}'],text=True).splitlines()
    records=[json.loads(subprocess.check_output(['docker','inspect',identity]))[0] for identity in identities]
    identity=choose_app(records,project)
    subprocess.run(['docker','exec',identity,'python','-m','backend.app.sms_worker'],check=True,timeout=40)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError):raise SystemExit('SMS worker unavailable; inspect service state without printing environment') from None
