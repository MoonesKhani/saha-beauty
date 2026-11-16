"""GitHub metadata stays on runner; signed URL travels only over verified SSH stdin."""
import json
import os
import re
import urllib.error
import urllib.request

class DownloadError(RuntimeError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def github_request(path,redirect=False):
    repo=os.environ.get('GITHUB_REPOSITORY','')
    token=os.environ.get('GH_TOKEN','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not token:
        raise DownloadError('GitHub artifact credentials unavailable')
    request=urllib.request.Request('https://api.github.com/repos/'+repo+path,
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:
            if redirect:raise DownloadError('Expected a signed artifact redirect')
            return json.load(response)
    except urllib.error.HTTPError as error:
        if redirect and error.code==302:
            location=error.headers.get('Location','');error.close()
            # Same allowlist as receiver; never include the signed URL in errors/logs.
            try:
                from .artifact_fetch import valid_url
            except ImportError:
                from artifact_fetch import valid_url
            try:return valid_url(location)
            except ValueError:raise DownloadError('Unexpected artifact download host') from None
        error.close();raise DownloadError('GitHub artifact lookup failed') from None
    except DownloadError:raise
    except Exception:raise DownloadError('GitHub artifact lookup failed') from None


def artifact(run_id,name,commit):
    if not str(run_id).isdigit():raise DownloadError('Invalid build run identity')
    data=github_request('/actions/runs/'+str(run_id)+'/artifacts?per_page=100')
    matches=[row for row in data.get('artifacts',[]) if row.get('name')==name and not row.get('expired')]
    if len(matches)!=1:raise DownloadError('Exactly one unexpired approved artifact is required')
    row=matches[0]
    if row.get('workflow_run',{}).get('head_sha')!=commit:raise DownloadError('Artifact source differs from approval')
    digest=row.get('digest','')
    if not re.fullmatch('sha256:[0-9a-f]{64}',digest):raise DownloadError('GitHub ZIP digest required')
    if type(row.get('size_in_bytes')) is not int or not 0<row['size_in_bytes']<=2*1024**3:raise DownloadError('Invalid ZIP size')
    return row


def stage(sender,run_id,name,probe=False,check=False):
    state=sender.request('status')
    if not state.get('artifact_fetch'):
        raise DownloadError('Receiver upgrade required for HTTPS artifacts; no slow SSH fallback or installation attempted')
    row=artifact(run_id,name,sender.commit)
    command=f'{sender.commit} {sender.digest} {sender.size} {row["digest"][7:]} {row["size_in_bytes"]}'
    # A fresh signed link on each attempt allows resumption without storing URLs.
    for attempt in range(2):
        location=github_request('/actions/artifacts/'+str(row['id'])+'/zip',redirect=True)
        message=json.dumps({'url':location}).encode()
        try:
            operation='probe-artifact ' if probe else 'check-artifact ' if check else 'fetch-artifact '
            result=sender.request(operation+command,message,timeout=35 if (probe or check) else 325)
            if probe:return result
            if result.get('complete') is not True or result.get('bytes')!=sender.size:
                raise DownloadError('Receiver did not verify the complete bundle')
            print('HTTPS artifact and release SHA-256 verified; installation remains separate',flush=True)
            return result
        except Exception:
            if attempt==1 or probe or check:raise
            # Only staging is retried. A failed/unknown application installation is not.
            sender.request('status')
