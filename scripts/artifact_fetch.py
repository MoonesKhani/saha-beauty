"""Fetch only signed GitHub Actions blobs over verified HTTPS; never install an image."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from .deploy_release import verify_bundle_file
except ImportError:
    from deploy_release import verify_bundle_file

MAX_BYTES=2*1024**3
SAMPLE=32*1024
class ArtifactError(ValueError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def valid_url(value):
    if not isinstance(value,str) or len(value)>16384:raise ArtifactError('Invalid artifact location')
    try:
        url=urllib.parse.urlsplit(value)
        valid=(url.scheme=='https' and url.username is None and url.password is None and url.port in (None,443)
            and re.fullmatch(r'productionresultssa[a-z0-9]*\.blob\.core\.windows\.net',url.hostname or '')
            and url.path not in ('','/') and not url.fragment)
    except ValueError:valid=False
    if not valid:raise ArtifactError('Only the signed GitHub Actions Azure artifact host is accepted')
    return value


def validate_spec(tar_hash,tar_size,zip_hash,zip_size):
    if not all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for h in (tar_hash,zip_hash)):
        raise ArtifactError('Invalid artifact checksum metadata')
    if not all(type(n) is int and 0<n<=MAX_BYTES for n in (tar_size,zip_size)):
        raise ArtifactError('Artifact exceeds the approved size limit')


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())


def open_range(url,offset,total,end=None,open_url=None):
    valid_url(url);end=total-1 if end is None else end
    request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{end}'},method='GET')
    try:
        response=(open_url or opener().open)(request,timeout=8)
        expected=f'bytes {offset}-{end}/{total}'
        if response.status!=206 or response.headers.get('Content-Range')!=expected:
            response.close();raise ArtifactError('Artifact server did not honor the exact byte range')
        return response
    except ArtifactError:raise
    except Exception:raise ArtifactError('HTTPS artifact connection failed; no installation requested') from None


def probe(url,size,open_url=None):
    if type(size) is not int or not 0<size<=MAX_BYTES:raise ArtifactError('Invalid artifact size')
    count=min(SAMPLE,size);start=time.monotonic()
    body=b''
    with open_range(url,0,size,count-1,open_url) as response:
        while len(body)<count:
            if time.monotonic()-start>15:raise ArtifactError('HTTPS probe budget exceeded')
            chunk=getattr(response,'read1',response.read)(count-len(body))
            if not chunk:break
            body+=chunk
    if len(body)!=count:raise ArtifactError('Incomplete HTTPS probe')
    seconds=max(time.monotonic()-start,.001)
    return {'https_ok':True,'sample_bytes':count,'seconds':round(seconds,3),'bytes_per_second':round(count/seconds),'installation_requested':False}


def fetch(url,destination,tar_hash,tar_size,zip_hash,zip_size,open_url=None,budget=300):
    validate_spec(tar_hash,tar_size,zip_hash,zip_size);valid_url(url)
    destination=Path(destination)
    if destination.exists():
        verify_bundle_file(destination,tar_size,tar_hash)
        return {'complete':True,'bytes':tar_size,'cached':True}
    partial=destination.parent/('artifact-'+zip_hash+'.part')
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>zip_size:raise ArtifactError('Invalid staged artifact size; installation blocked')
    deadline=time.monotonic()+budget
    if offset<zip_size:
        with open_range(url,offset,zip_size,open_url=open_url) as response,partial.open('ab') as output:
            os.chmod(partial,0o600)
            try:
                while offset<zip_size:
                    if time.monotonic()>deadline:raise ArtifactError('HTTPS download budget exceeded; partial retained for resume')
                    read=getattr(response,'read1',response.read)
                    chunk=read(min(65536,zip_size-offset))
                    if not chunk:raise ArtifactError('HTTPS download interrupted; partial retained for resume')
                    output.write(chunk);offset+=len(chunk)
            except ArtifactError:raise
            except Exception:raise ArtifactError('HTTPS download interrupted; partial retained for resume') from None
            finally:output.flush();os.fsync(output.fileno())
    digest=hashlib.sha256()
    with partial.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):digest.update(chunk)
    if partial.stat().st_size!=zip_size or digest.hexdigest()!=zip_hash:
        raise ArtifactError('Artifact ZIP checksum mismatch; installation blocked')
    try:
        with zipfile.ZipFile(partial) as archive,tempfile.TemporaryDirectory(prefix='artifact-unpack-',dir=destination.parent) as temporary:
            entries=archive.infolist()
            if len(entries)!=2 or {x.filename for x in entries}!={'release.tar','release.tar.sha256'}:
                raise ArtifactError('Unexpected artifact members')
            for item in entries:
                if item.is_dir() or stat.S_ISLNK(item.external_attr>>16):raise ArtifactError('Unsafe artifact member')
                if item.filename=='release.tar' and item.file_size!=tar_size:raise ArtifactError('Artifact bundle size mismatch')
                if item.filename.endswith('.sha256') and item.file_size>256:raise ArtifactError('Artifact checksum file too large')
            checksum=archive.read('release.tar.sha256').decode('ascii').split()
            if checksum!=[tar_hash,'release.tar']:raise ArtifactError('Artifact bundle checksum metadata mismatch')
            target=Path(temporary)/'release.tar'
            with archive.open('release.tar') as source,target.open('xb') as output:
                os.chmod(target,0o600);count=0
                while chunk:=source.read(1024*1024):
                    count+=len(chunk)
                    if count>tar_size:raise ArtifactError('Artifact extraction size exceeded')
                    output.write(chunk)
                output.flush();os.fsync(output.fileno())
            verify_bundle_file(target,tar_size,tar_hash)
            os.replace(target,destination)
    except ArtifactError:raise
    except Exception:raise ArtifactError('Invalid or incomplete artifact archive; installation blocked') from None
    partial.unlink()
    return {'complete':True,'bytes':tar_size,'cached':False}
