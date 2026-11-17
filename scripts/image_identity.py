"""Prove config/manifest identity equivalence from an already verified image archive.

Docker's classic and containerd stores expose different image IDs. Never infer
identity from revision labels alone; follow content-addressed archive metadata.
"""
import hashlib
import json
import re
import tarfile

DIGEST=re.compile(r'sha256:[0-9a-f]{64}')
BLOB=re.compile(r'blobs/sha256/([0-9a-f]{64})')
CONFIG=re.compile(r'([0-9a-f]{64})\.json')
INDEX_TYPES={'application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json'}
MANIFEST_TYPES={'application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'}

class ImageIdentityError(ValueError):pass

class SavedImageIdentities:
    def __init__(self,path):
        self.blobs={};self.sizes={};self.memo={};total=0
        try:
            source=tarfile.open(fileobj=path,mode='r:*') if hasattr(path,'read') else tarfile.open(path,'r:*')
            with source as archive:
                for item in archive:
                    match=BLOB.fullmatch(item.name) or CONFIG.fullmatch(item.name)
                    if not match or not item.isfile() or not 0<item.size<=1024*1024:continue
                    raw=archive.extractfile(item).read();total+=len(raw)
                    if total>16*1024*1024:raise ImageIdentityError('Image metadata exceeds the bounded proof limit')
                    try:data=json.loads(raw)
                    except (ValueError,UnicodeError):continue
                    if not isinstance(data,dict):continue
                    digest='sha256:'+match[1]
                    if hashlib.sha256(raw).hexdigest()!=match[1]:raise ImageIdentityError('Image metadata content digest mismatch')
                    if digest in self.blobs:raise ImageIdentityError('Duplicate image metadata digest')
                    self.blobs[digest]=data;self.sizes[digest]=len(raw)
        except (tarfile.TarError,OSError,EOFError):raise ImageIdentityError('Cannot read verified image metadata') from None

    def config_ids(self,digest,platform,seen=None):
        seen=set() if seen is None else set(seen)
        if not isinstance(digest,str) or not DIGEST.fullmatch(digest) or digest in seen or len(seen)>=8:
            raise ImageIdentityError('Invalid or recursive image identity graph')
        cache=(digest,platform)
        if cache in self.memo:return set(self.memo[cache])
        seen.add(digest);node=self.blobs.get(digest)
        if not node:raise ImageIdentityError('Image identity is absent from the verified archive')
        rootfs=node.get('rootfs') or {}
        if not isinstance(rootfs,dict):raise ImageIdentityError('Invalid image filesystem metadata')
        if rootfs.get('type')=='layers':
            return {digest} if (node.get('os'),node.get('architecture'))==platform else set()
        if node.get('schemaVersion')!=2:raise ImageIdentityError('Unrecognized image descriptor schema')
        media=node.get('mediaType')
        if not isinstance(media,str):raise ImageIdentityError('Invalid image descriptor media type')
        if media in INDEX_TYPES:
            children=node.get('manifests')
            if not isinstance(children,list) or len(children)>32:raise ImageIdentityError('Unbounded image index')
        elif media in MANIFEST_TYPES:children=[node.get('config')]
        else:raise ImageIdentityError('Unsupported image descriptor type')
        result=set()
        for child in children:
            if not isinstance(child,dict):raise ImageIdentityError('Invalid image descriptor')
            selected=child.get('platform') or {}
            if not isinstance(selected,dict):raise ImageIdentityError('Invalid image platform metadata')
            if selected and (selected.get('os'),selected.get('architecture'))!=platform:continue
            target=child.get('digest')
            if not isinstance(target,str) or not DIGEST.fullmatch(target):raise ImageIdentityError('Invalid image descriptor digest')
            if type(child.get('size')) is not int or self.sizes.get(target)!=child.get('size'):raise ImageIdentityError('Image descriptor size mismatch')
            result.update(self.config_ids(target,platform,seen))
        self.memo[cache]=frozenset(result)
        return result

    def verify(self,record,actual):
        platform=(actual.get('Os'),actual.get('Architecture'))
        if platform!=('linux','amd64'):raise ImageIdentityError('Only the reviewed linux/amd64 platform is supported')
        expected=self.config_ids(record['image_id'],platform)
        observed=self.config_ids(actual.get('Id'),platform)
        if len(expected)!=1 or expected!=observed:raise ImageIdentityError('Loaded image content differs from the approved image')
        config=self.blobs[next(iter(expected))]
        if (actual.get('RootFS') or {}).get('Layers')!=(config.get('rootfs') or {}).get('diff_ids'):
            raise ImageIdentityError('Loaded filesystem layers differ from the approved configuration')
        original=config.get('config') or {};loaded=actual.get('Config') or {}
        def normalized(value):return None if value in (None,'',[],{}) else value
        for key in ['Env','Cmd','Entrypoint','User','WorkingDir','Labels','ExposedPorts','Volumes','Healthcheck','StopSignal','Shell']:
            if normalized(original.get(key))!=normalized(loaded.get(key)):
                raise ImageIdentityError('Loaded executable configuration differs from the approved image: '+key)
        if (loaded.get('Labels') or {}).get('org.opencontainers.image.revision')!=record['commit']:
            raise ImageIdentityError('Loaded image revision differs from approval')
        return actual['Id']
