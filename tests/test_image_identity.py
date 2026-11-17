from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from scripts.image_identity import SavedImageIdentities,ImageIdentityError
from scripts.deploy_release import ComposeEngine,DeploymentError,atomic_json

COMMIT='a'*40
class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.config={'architecture':'amd64','os':'linux','rootfs':{'type':'layers','diff_ids':['sha256:'+'d'*64]},'config':{'Env':['PATH=/bin'],'Cmd':['python','app.py'],'User':'saha','WorkingDir':'/app','Labels':{'org.opencontainers.image.revision':COMMIT}}}
        self.entries={};self.config_id=self.blob(self.config)
        self.manifest={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json','config':self.desc(self.config_id)}
        self.manifest_id=self.blob(self.manifest)
        self.index_id=self.blob({'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':[{**self.desc(self.manifest_id),'platform':{'os':'linux','architecture':'amd64'}}]})
        self.actual={'Id':self.manifest_id,'Os':'linux','Architecture':'amd64','RootFS':{'Type':'layers','Layers':self.config['rootfs']['diff_ids']},'Config':deepcopy(self.config['config'])}
        self.record={'commit':COMMIT,'image_id':self.config_id,'image_tag':'fixture:'+COMMIT}
    def blob(self,value):
        raw=json.dumps(value,sort_keys=True).encode();identity='sha256:'+hashlib.sha256(raw).hexdigest();self.entries['blobs/sha256/'+identity[7:]]=raw;return identity
    def desc(self,identity):return {'digest':identity,'size':len(self.entries['blobs/sha256/'+identity[7:]])}
    def archive(self):
        path=self.root/'images.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for name,data in self.entries.items():
                item=tarfile.TarInfo(name);item.size=len(data);archive.addfile(item,BytesIO(data))
        return path
    def test_config_and_manifest_ids_prove_the_exact_same_content(self):
        proof=SavedImageIdentities(self.archive())
        self.assertEqual(proof.verify(self.record,self.actual),self.manifest_id)
        self.assertEqual(proof.verify({**self.record,'image_id':self.manifest_id},{**self.actual,'Id':self.config_id}),self.config_id)
    def test_index_resolves_only_the_reviewed_platform(self):
        self.assertEqual(SavedImageIdentities(self.archive()).verify({**self.record,'image_id':self.index_id},self.actual),self.manifest_id)
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive()).verify(self.record,{**self.actual,'Architecture':'arm64'})
    def test_matching_revision_labels_do_not_authorize_different_content(self):
        other=deepcopy(self.config);other['config']['Cmd']=['unapproved.py'];other_id=self.blob(other)
        manifest=self.blob({**self.manifest,'config':self.desc(other_id)})
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive()).verify(self.record,{**self.actual,'Id':manifest})
    def test_unknown_runtime_digest_is_rejected(self):
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive()).verify(self.record,{**self.actual,'Id':'sha256:'+'f'*64})
    def test_inspect_command_or_filesystem_difference_is_rejected(self):
        for field in ['Cmd','Env','User','Labels']:
            actual=deepcopy(self.actual);actual['Config'][field]='changed-private-fixture'
            with self.subTest(field=field),self.assertRaises(ImageIdentityError) as error:SavedImageIdentities(self.archive()).verify(self.record,actual)
            self.assertNotIn('private-fixture',str(error.exception))
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive()).verify(self.record,{**self.actual,'RootFS':{'Layers':['wrong']}})
    def test_tampered_metadata_is_rejected_before_aliasing(self):
        self.entries['blobs/sha256/'+self.config_id[7:]]=b'{"tampered":true}'
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive())
    def test_descriptor_size_difference_is_rejected(self):
        bad=self.blob({**self.manifest,'config':{**self.desc(self.config_id),'size':1}})
        with self.assertRaises(ImageIdentityError):SavedImageIdentities(self.archive()).verify(self.record,{**self.actual,'Id':bad})
    def test_verified_runtime_reference_is_used_by_compose_and_retained_state(self):
        engine=ComposeEngine.__new__(ComposeEngine);engine.project=self.root;engine.resolved_images=[]
        record={**self.record,'runtime_image_id':self.manifest_id};atomic_json(self.root/'.deploy/state.json',{'current':record})
        engine.compose=lambda *args:['compose']
        def run(args,label,**kwargs):
            if label=='find current app':return 'container'
            if label=='inspect current image':return json.dumps([self.actual])
            if label=='retain rollback image':
                self.assertEqual(args[3],self.manifest_id);return ''
            raise AssertionError(label)
        engine.run=run;engine.inspect=lambda identity:{'State':{'Status':'running'},'Image':self.config_id}
        observed=engine.current();self.assertEqual(observed['image_id'],self.config_id);self.assertEqual(observed['runtime_image_id'],self.manifest_id)
        target=self.root/'overlay.json';engine.overlay(record,target)
        self.assertEqual(json.loads(target.read_text())['services']['app']['image'],self.manifest_id)
    def test_invalid_runtime_reference_is_rejected(self):
        with self.assertRaises(DeploymentError):ComposeEngine.image_reference({**self.record,'runtime_image_id':'unapproved:latest'})
    def test_verified_existing_image_is_reused_and_untrusted_runtime_field_removed(self):
        engine=ComposeEngine.__new__(ComposeEngine);engine.project=self.root;engine.resolved_images=[]
        info={**self.actual,'Id':self.config_id}
        calls=[]
        def run(args,label,**kwargs):
            calls.append(label)
            if label=='inspect approved image':return json.dumps([info])
            raise AssertionError('Existing verified image must not be reloaded')
        engine.run=run;record={**self.record,'runtime_image_id':'sha256:'+'e'*64}
        engine.load(record,self.archive())
        self.assertNotIn('runtime_image_id',record);self.assertEqual(calls,['inspect approved image'])
    def test_missing_image_is_loaded_then_verified(self):
        engine=ComposeEngine.__new__(ComposeEngine);engine.project=self.root;engine.resolved_images=[]
        ready=False
        def run(args,label,**kwargs):
            nonlocal ready
            if label=='load approved image':ready=True;return ''
            if label=='inspect approved image':
                if not ready:raise DeploymentError('Image missing')
                return json.dumps([{**self.actual,'Id':self.config_id}])
            raise AssertionError(label)
        engine.run=run;engine.load(dict(self.record),self.archive());self.assertTrue(ready)
    def test_switch_compares_resolved_image_not_container_reference_spelling(self):
        engine=ComposeEngine.__new__(ComposeEngine);engine.managed=self.root/'managed.json';engine.mounts=[]
        record={**self.record,'runtime_image_id':self.manifest_id}
        engine.compose=lambda *args:['compose']
        def run(args,label,**kwargs):
            if label=='switch app image':return ''
            if label=='find switched app':return 'container'
            if label=='verify switched image identity':return json.dumps([self.actual])
            raise AssertionError(label)
        engine.run=run;engine.inspect=lambda identity:{'Image':self.config_id,'Mounts':[]}
        engine.switch(record)
        self.assertEqual(json.loads(engine.managed.read_text())['services']['app']['image'],self.manifest_id)
