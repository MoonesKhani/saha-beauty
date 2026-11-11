from dataclasses import replace
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings, ROOT
from backend.app.main import create_app
from frontend.build import build

TOKEN='upload-fixture-'+('x'*40)
AUTH={'Authorization':'Bearer '+TOKEN}
UPLOAD={'Content-Type':'audio/mpeg','X-Saha-Audio-Upload':'1'}
@pytest.fixture
def settings(tmp_path):
    return Settings(frontend_dir=build(tmp_path/'frontend'),database_url=f'sqlite:///{tmp_path / "db.sqlite"}',audio_upload_dir=tmp_path/'private',audio_upload_enabled=True,admin_api_token=TOKEN)

def test_upload_persists_privately_and_can_be_managed(settings):
    content=(ROOT/'assets/saha-quiet-bloom.mp3').read_bytes()
    with TestClient(create_app(settings)) as c:
        response=c.post('/api/v1/audio-submissions',content=content,headers=UPLOAD)
        assert response.status_code==201,response.text
        ident=response.json()['id']
        assert response.json()['status']=='pending_review'
        assert (settings.audio_upload_dir/(ident+'.audio')).read_bytes()==content
        assert c.get('/api/v1/admin/audio-submissions').status_code==401
        assert c.get('/api/v1/admin/audio-submissions/'+ident).status_code==401
        assert c.get('/assets/'+ident+'.audio').status_code==404
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/v1/admin/audio-submissions',headers=AUTH).json()['items'][0]['id']==ident
        assert c.get('/api/v1/admin/audio-submissions/'+ident,headers=AUTH).content==content
        assert c.delete('/api/v1/admin/audio-submissions/'+ident,headers=AUTH).status_code==204
        assert not list(settings.audio_upload_dir.glob('*.audio'))

def test_rejects_bad_uploads_and_cleans_up(settings):
    with TestClient(create_app(settings)) as c:
        for content in [b'', b'this is not an mp3',b'<html><script>alert(1)</script></html>']:
            assert c.post('/api/v1/audio-submissions',content=content,headers=UPLOAD).status_code==422
        assert c.post('/api/v1/audio-submissions',content=b'abc',headers={'Content-Type':'text/html','X-Saha-Audio-Upload':'1'}).status_code==415
        assert c.post('/api/v1/audio-submissions',content=b'abc',headers={'Content-Type':'audio/mpeg'}).status_code==400
        assert c.post('/api/v1/audio-submissions',content=b'abc',headers={**UPLOAD,'Origin':'https://other.example'}).status_code==403
        assert c.post('/api/v1/audio-submissions',content=b'abc',headers={**UPLOAD,'Content-Length':str(26*1024*1024)}).status_code==413
        assert not list(settings.audio_upload_dir.glob('*.part'))
        assert not list(settings.audio_upload_dir.glob('*.audio'))

def test_disabled_or_unmanageable_uploads_are_unavailable(settings):
    for config in [replace(settings,audio_upload_enabled=False),replace(settings,admin_api_token='')]:
        with TestClient(create_app(config)) as c:
            assert c.get('/api/v1/audio-submissions/status').status_code==503
            assert c.post('/api/v1/audio-submissions',content=b'x',headers=UPLOAD).status_code==503

def test_quota_and_lock(settings):
    import fcntl
    settings.audio_upload_dir.mkdir()
    with (settings.audio_upload_dir/'.upload.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with TestClient(create_app(settings)) as c:
            assert c.post('/api/v1/audio-submissions',content=b'x',headers=UPLOAD).status_code==429
    with TestClient(create_app(replace(settings,audio_upload_quota=1))) as c:
        assert c.post('/api/v1/audio-submissions',content=b'x',headers=UPLOAD).status_code==507
