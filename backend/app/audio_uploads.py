"""Private persistent audio submissions. Serve behind a same-origin HTTPS proxy."""
import asyncio
import fcntl
import json
import os
import time
import uuid
from pathlib import Path
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse

MAX_FILE = 25 * 1024 * 1024
ALLOWED_FORMATS = {'mp3', 'wav', 'flac', 'ogg', 'aac', 'mov', 'mp4', 'm4a'}

def mount_audio_uploads(app, settings, require_admin):
    directory = settings.audio_upload_dir

    def available():
        if not settings.audio_upload_enabled or len(settings.admin_api_token) < 32:
            raise HTTPException(503, 'دریافت فایل هنوز روی سرور فعال نشده است.')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    @app.get('/api/v1/audio-submissions/status')
    def upload_status():
        available()
        return {'enabled': True, 'max_bytes': MAX_FILE}

    @app.post('/api/v1/audio-submissions', status_code=201)
    async def upload(request: Request):
        available()
        # Browser requests are same-origin only; never trust a forwarded host.
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'درخواست باید از همین سایت ارسال شود.')
        if request.headers.get('x-saha-audio-upload') != '1':
            raise HTTPException(400, 'درخواست آپلود معتبر نیست.')
        if request.headers.get('content-type', '').split(';')[0] not in {'audio/mpeg','audio/mp3','audio/wav','audio/x-wav','audio/wave','audio/flac','audio/ogg','audio/aac','audio/mp4','audio/x-m4a'}:
            raise HTTPException(415, 'نوع فایل صوتی پشتیبانی نمی‌شود.')
        try:
            declared = int(request.headers.get('content-length', '0'))
        except ValueError:
            raise HTTPException(400, 'اندازه فایل معتبر نیست.')
        if declared > MAX_FILE:
            raise HTTPException(413, 'حداکثر اندازه فایل ۲۵ مگابایت است.')
        # Shared nonblocking lock bounds upload disk usage across server workers.
        lock = (directory / '.upload.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise HTTPException(429, 'یک فایل در حال دریافت است؛ کمی بعد تلاش کن.', headers={'Retry-After':'15'})
        ident = str(uuid.uuid4())
        temporary = directory / (ident + '.part')
        destination = directory / (ident + '.audio')
        metadata = directory / (ident + '.json')
        success = False
        try:
            used = sum(p.stat().st_size for p in directory.glob('*.audio'))
            if used + MAX_FILE > settings.audio_upload_quota:
                raise HTTPException(507, 'فضای دریافت فایل پر شده است؛ به سالن خبر بده.')
            size = 0
            async def receive():
                nonlocal size
                with temporary.open('xb') as output:
                    os.chmod(temporary, 0o600)
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_FILE:
                            raise HTTPException(413, 'حداکثر اندازه فایل ۲۵ مگابایت است.')
                        output.write(chunk)
                    output.flush(); os.fsync(output.fileno())
            try:
                await asyncio.wait_for(receive(), timeout=120)
            except asyncio.TimeoutError:
                raise HTTPException(408, 'زمان دریافت فایل تمام شد؛ دوباره تلاش کن.')
            if not size:
                raise HTTPException(422, 'فایل خالی است.')
            try:
                process = await asyncio.create_subprocess_exec('ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=format_name,duration:stream=codec_type','-of','json',str(temporary),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            except FileNotFoundError:
                raise HTTPException(503, 'بررسی فایل صوتی روی سرور آماده نیست.')
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                process.kill(); await process.wait()
                raise HTTPException(422, 'بررسی فایل صوتی کامل نشد.')
            try:
                info = json.loads(output)
                streams = info['streams']
                formats = set(info['format']['format_name'].split(','))
                valid = process.returncode == 0 and streams and all(s['codec_type'] == 'audio' for s in streams) and bool(formats & ALLOWED_FORMATS) and 0 < float(info['format']['duration']) <= 3600
            except (ValueError, KeyError, TypeError):
                valid = False
            if not valid:
                raise HTTPException(422, 'فایل باید صوتی سالم و حداکثر یک ساعت باشد.')
            temporary.replace(destination)
            record = {'id':ident, 'bytes':size, 'created_at':time.time(), 'status':'pending_review', 'content_type':request.headers['content-type'].split(';')[0]}
            with metadata.open('x') as file:
                os.chmod(metadata, 0o600); json.dump(record, file); file.flush(); os.fsync(file.fileno())
            success = True
            return {'id':ident, 'status':'pending_review'}
        finally:
            temporary.unlink(missing_ok=True)
            if not success:
                destination.unlink(missing_ok=True); metadata.unlink(missing_ok=True)
            lock.close()

    def paths(ident):
        try:
            if str(uuid.UUID(ident)) != ident:
                raise ValueError()
        except ValueError:
            raise HTTPException(404, 'فایل پیدا نشد.')
        audio, meta = directory / (ident+'.audio'), directory / (ident+'.json')
        if not audio.is_file() or not meta.is_file():
            raise HTTPException(404, 'فایل پیدا نشد.')
        return audio, meta

    @app.get('/api/v1/admin/audio-submissions', dependencies=[Depends(require_admin)])
    def submissions():
        available()
        return {'items':[json.loads(meta.read_text()) for meta in sorted(directory.glob('*.json')) if meta.with_suffix('.audio').is_file()]}

    @app.get('/api/v1/admin/audio-submissions/{ident}', dependencies=[Depends(require_admin)])
    def download(ident: str):
        available(); audio, meta = paths(ident)
        record = json.loads(meta.read_text())
        return FileResponse(audio, media_type=record['content_type'], filename=ident+'.audio', headers={'Cache-Control':'no-store'})

    @app.delete('/api/v1/admin/audio-submissions/{ident}', dependencies=[Depends(require_admin)], status_code=204)
    def delete(ident: str):
        available(); audio, meta = paths(ident)
        meta.unlink(); audio.unlink(missing_ok=True)
