"""Runner-only private S3 staging. Server receives a short-lived URL, never S3 keys."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
try:
    from .artifact_fetch import storage_policy,storage_policy_hash,valid_url,MAX_BYTES
    from .https_release import DownloadError
except ImportError:
    from artifact_fetch import storage_policy,storage_policy_hash,valid_url,MAX_BYTES
    from https_release import DownloadError


CONFIG_FILE=Path(__file__).resolve().parents[1]/'deploy/arvan-transfer.json'


def configuration():
    try:
        defaults=json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
        return storage_policy({field:os.environ.get('ARVAN_STORAGE_'+field.upper()) or defaults.get(field,'saha-releases/' if field=='prefix' else '')
            for field in ['endpoint','bucket','region','prefix']})
    except (OSError,ValueError,TypeError,AttributeError):
        raise DownloadError('Configure the exact Arvan endpoint, bucket, region and release prefix first') from None


def client(config):
    access=os.environ.get('ARVAN_STORAGE_ACCESS_KEY_ID','');secret=os.environ.get('ARVAN_STORAGE_SECRET_ACCESS_KEY','')
    if not access or not secret:raise DownloadError('Arvan storage credentials unavailable; no upload or installation requested')
    import boto3
    from botocore.config import Config
    return boto3.client('s3',endpoint_url=config['endpoint'],region_name=config['region'],
        aws_access_key_id=access,aws_secret_access_key=secret,
        config=Config(signature_version='s3v4',connect_timeout=5,read_timeout=20,
            retries={'mode':'standard','total_max_attempts':3},s3={'addressing_style':'path'},
            request_checksum_calculation='when_required',response_checksum_validation='when_required'))


def prepare_zip(sender):
    if not 0<sender.size<MAX_BYTES-10240:raise DownloadError('Arvan release exceeds the bounded archive size')
    target=sender.bundle.parent/('arvan-'+sender.digest+'.zip')
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
        info=zipfile.ZipInfo('release.tar');info.external_attr=0o600<<16
        with archive.open(info,'w',force_zip64=True) as output,sender.bundle.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):output.write(block)
        info=zipfile.ZipInfo('release.tar.sha256');info.external_attr=0o600<<16
        archive.writestr(info,sender.digest+'  release.tar\n')
    with target.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    return target,digest


def publish(storage,config,archive,digest,release_digest,commit):
    key=config['prefix']+commit+'/'+digest+'.zip'
    metadata={'sha256':digest,'release-sha256':release_digest}
    try:
        from boto3.s3.transfer import TransferConfig
        print('Uploading verified bundle to private Arvan storage',flush=True)
        storage.upload_file(str(archive),config['bucket'],key,
            ExtraArgs={'ACL':'private','ContentType':'application/zip','Metadata':metadata},
            Config=TransferConfig(multipart_threshold=8*1024**2,multipart_chunksize=8*1024**2,max_concurrency=2))
        info=storage.head_object(Bucket=config['bucket'],Key=key)
        if info.get('ContentLength')!=archive.stat().st_size or info.get('Metadata')!=metadata:
            raise DownloadError('Arvan uploaded size/metadata mismatch; installation blocked')
    except DownloadError:raise
    except Exception:raise DownloadError('Arvan upload/verification failed; check endpoint, private bucket and scoped permissions; installation NOT requested') from None
    return key


def stage(sender,probe=False,check=False):
    config=configuration()
    state=sender.request('status')
    if not state.get('arvan_fetch') or state.get('arvan_policy_hash')!=storage_policy_hash(config):
        raise DownloadError('Install and pin this exact Arvan destination on the receiver first; no upload or installation attempted')
    if not (probe or check):
        cached=sender.query() # Receiver rechecks the exact approved tar size/SHA-256.
        if cached.get('complete') is True and cached.get('bytes')==sender.size:
            print('Exact approved bundle already verified on receiver; reusing it without upload/download',flush=True)
            return cached
    archive,digest=prepare_zip(sender);storage=client(config)
    key=publish(storage,config,archive,digest,sender.digest,sender.commit)
    command=f'{sender.commit} {sender.digest} {sender.size} {digest} {archive.stat().st_size}'
    for attempt in range(2):
        try:
            location=storage.generate_presigned_url('get_object',Params={'Bucket':config['bucket'],'Key':key},ExpiresIn=600)
            valid_url(location,policy=config)
        except Exception:raise DownloadError('Cannot create an approved short-lived Arvan download URL') from None
        operation='probe-artifact ' if probe else 'check-artifact ' if check else 'fetch-artifact '
        try:
            result=sender.request(operation+command,json.dumps({'url':location}).encode(),timeout=35 if (probe or check) else 325)
            if probe:return result
            if result.get('complete') is not True or result.get('bytes')!=sender.size:
                raise DownloadError('Arvan bundle not fully verified; installation blocked')
            print('Arvan bundle size and SHA-256 verified; installation remains separate',flush=True)
            return result
        except Exception:
            if attempt or probe or check:raise
            sender.request('status') # Read only before retrying staging, never installation.
