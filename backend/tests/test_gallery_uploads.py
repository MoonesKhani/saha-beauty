from dataclasses import replace
from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend.app.cli import upgrade_database, seed_database
from backend.app.config import Settings
from backend.app.main import create_app
from frontend.build import build

TOKEN='gallery-upload-test-'+'x'*40
AUTH={'Authorization':'Bearer '+TOKEN,'Content-Type':'image/png'}
@pytest.fixture
def setup(tmp_path):
    url=f'sqlite:///{tmp_path / "gallery.db"}'
    upgrade_database(url);seed_database(url)
    settings=Settings(database_url=url,admin_api_token=TOKEN,frontend_dir=build(tmp_path/'frontend'),gallery_upload_dir=tmp_path/'gallery')
    with TestClient(create_app(settings)) as client:yield client,settings

def picture(width=80,height=40):
    image=Image.new('RGB',(width,height),'pink');output=BytesIO()
    metadata=Image.Exif();metadata[271]='private metadata fixture'
    image.save(output,format='PNG',exif=metadata)
    return output.getvalue()

def upload(client,data=None,headers=None):
    return client.post('/api/v1/admin/gallery-upload',content=picture() if data is None else data,headers=AUTH if headers is None else headers)

def test_image_upload_publication_and_archival(setup):
    client,settings=setup
    response=upload(client);assert response.status_code==201,response.text
    src=response.json()['src'];assert src.startswith('/media/gallery/') and src.endswith('.webp')
    assert client.get(src).status_code==404 # Upload alone does not publish the image.
    row=client.post('/api/v1/admin/gallery',headers={'Authorization':'Bearer '+TOKEN},json={'title':'نمونه تأییدشده','src':src,'category':'bride','staff_code':'01','is_active':True})
    assert row.status_code==201,row.text
    public=client.get(src);assert public.status_code==200 and public.headers['content-type']=='image/webp'
    with Image.open(BytesIO(public.content)) as image:
        assert image.size==(80,40) and not image.getexif()
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(src).content==public.content
        assert restarted.get('/api/v1/gallery').json()['items'][0]['src']==src
    assert client.delete('/api/v1/admin/gallery/'+row.json()['id']+'?revision=1',headers=AUTH).status_code==200
    assert client.get(src).status_code==404

def test_upload_auth_type_corruption_and_origin(setup):
    client,settings=setup
    assert upload(client,headers={'Content-Type':'image/png'}).status_code==401
    assert upload(client,headers={**AUTH,'Content-Type':'text/html'}).status_code==415
    assert upload(client,b'not an image').status_code==422
    assert upload(client,headers={**AUTH,'Origin':'https://other.example'}).status_code==403
    assert upload(client,headers={**AUTH,'Content-Type':'image/jpeg'}).status_code==422
    assert not list(settings.gallery_upload_dir.glob('*.webp'))

def test_upload_limits_and_thumbnail(setup):
    client,settings=setup
    assert upload(client,b'x'*(10*1024*1024+1)).status_code==413
    with TestClient(create_app(replace(settings,gallery_upload_quota=1))) as limited:
        assert upload(limited).status_code==413
    response=upload(client,picture(3000,1000));assert response.status_code==201
    assert response.json()['width']==2560 and response.json()['height']<1000
    assert not list(settings.gallery_upload_dir.glob('*.part'))
