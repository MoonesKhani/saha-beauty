"""Authenticated persistent portfolio uploads, re-encoded without image metadata."""
import fcntl
from io import BytesIO
import os
import re
from uuid import uuid4
import warnings
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from .models import GalleryImage

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
TYPES = {'image/jpeg':'JPEG', 'image/png':'PNG', 'image/webp':'WEBP'}

def mount_gallery_uploads(app, settings, session, require_admin):
    directory = settings.gallery_upload_dir

    @app.post('/api/v1/admin/gallery-upload', dependencies=[Depends(require_admin)], status_code=201)
    async def upload(request: Request):
        if request.headers.get('content-type','').split(';')[0] not in TYPES:
            raise HTTPException(415,'تصویر JPG، PNG یا WebP انتخاب کنید.')
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'تصویر را از همین سایت بارگذاری کنید.')
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_BYTES:
                raise HTTPException(413,'حداکثر اندازه تصویر ۱۰ مگابایت است.')
            data.extend(chunk)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format!=TYPES[request.headers['content-type'].split(';')[0]] or image.width*image.height>MAX_PIXELS:
                        raise ValueError('unsupported image')
                    image.load()
                    normalized=ImageOps.exif_transpose(image).convert('RGBA' if 'A' in image.getbands() else 'RGB')
                    normalized.thumbnail((2560,2560))
                    output=BytesIO()
                    normalized.save(output,format='WEBP',quality=88,exif=b'',icc_profile=None)
                    encoded=output.getvalue()
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise HTTPException(422,'فایل تصویر معتبر نیست یا ابعاد آن بیش از حد مجاز است.') from None
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        name=uuid4().hex+'.webp'
        with (directory/'.upload.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            used=sum(p.stat().st_size for p in directory.glob('*.webp'))
            if used+len(encoded)>settings.gallery_upload_quota:
                raise HTTPException(413,'فضای تصاویر پر شده است؛ با پشتیبانی سالن هماهنگ کنید.')
            temporary=directory/(name+'.part')
            try:
                with temporary.open('xb') as target:
                    target.write(encoded)
                os.replace(temporary,directory/name)
            finally:
                temporary.unlink(missing_ok=True)
        return {'src':'/api/v1/gallery-media/'+name,'width':normalized.width,'height':normalized.height,'bytes':len(encoded)}

    @app.get('/api/v1/gallery-media/{filename}')
    @app.get('/media/gallery/{filename}')
    def image(filename:str,db=Depends(session)):
        if not re.fullmatch(r'[0-9a-f]{32}\.webp',filename):raise HTTPException(404,'تصویر پیدا نشد.')
        src='/media/gallery/'+filename
        if not db.scalar(select(GalleryImage.id).where(GalleryImage.src.in_([src,'/api/v1/gallery-media/'+filename]),GalleryImage.is_active.is_(True)).limit(1)):
            raise HTTPException(404,'تصویر منتشر نشده است.')
        path=directory/filename
        if not path.is_file():raise HTTPException(404,'تصویر پیدا نشد.')
        return FileResponse(path,media_type='image/webp',headers={'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'})
