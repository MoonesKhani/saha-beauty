#!/usr/bin/env python3
"""Interactive server-only secret setup. Does not enable sending/restart/migrate/deploy."""
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import warnings
from urllib.parse import urlsplit


def updated_environment(text, values):
    lines=[]
    for line in text.splitlines():
        key=line.partition('=')[0].strip()
        if key not in values:lines.append(line)
    lines.extend(key+'='+value for key,value in values.items())
    return '\n'.join(lines)+'\n'


def hidden_input():
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass('کلید/آدرس محرمانه ملی پیامک: ').strip()
        except (getpass.GetPassWarning, EOFError):
            raise SystemExit('ورود پنهان در این محیط ممکن نیست؛ از ترمینال Termius استفاده کنید. چیزی تغییر نکرد.') from None


def backup_environment(env, directory=Path('/opt/saha-deploy/env-backups')):
    # Outside the checkout: safe even before its new .gitignore is installed.
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(directory,0o700)
    backup=Path(tempfile.mkdtemp(prefix='sms-',dir=directory))
    os.chmod(backup,0o700)
    shutil.copyfile(env,backup/'environment');os.chmod(backup/'environment',0o600)
    return backup


def main():
    if os.geteuid()!=0:raise SystemExit('این مرحله را در Termius با root اجرا کنید.')
    config=Path('/opt/saha-deploy/config.json')
    if not config.exists():raise SystemExit('تنظیمات استقرار موجود پیدا نشد؛ چیزی تغییر نکرد.')
    project=Path(json.loads(config.read_text())['project']).resolve();env=project/'.env'
    if not env.is_file() or env.is_symlink():raise SystemExit('فایل محیطی معمولی پروژه موجود لازم است؛ چیزی تغییر نکرد.')
    lock=(project/'.deploy/deploy.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('انتشار دیگری در حال اجراست؛ چیزی تغییر نکرد.') from None
    print('کلید یا آدرس OTP را اینجا وارد کنید؛ ورودی نمایش داده نمی‌شود. ارسال پیامک فعال نخواهد شد.')
    value=hidden_input()
    if value.startswith('https://'):
        url=urlsplit(value)
        if url.netloc!='console.melipayamak.com' or not url.path.startswith('/api/send/otp/') or url.query or url.fragment:
            raise SystemExit('آدرس معتبر OTP ملی پیامک لازم است؛ چیزی تغییر نکرد.')
        value=url.path[len('/api/send/otp/') :]
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value):raise SystemExit('قالب کلید معتبر نیست؛ چیزی تغییر نکرد.')
    text=env.read_text();previous={}
    for line in text.splitlines():
        key,separator,content=line.partition('=')
        if separator:previous[key.strip()]=content.strip().strip('\'"')
    secret=previous.get('SAHA_OTP_SECRET','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',secret):secret=secrets.token_urlsafe(48)
    values={'MELIPAYAMAK_API_KEY':value,'SAHA_OTP_SECRET':secret,
        'SAHA_OTP_ENABLED':'0','SAHA_SMS_LIVE_ENABLED':'0','SAHA_SMS_NOTIFICATIONS_ENABLED':'0',
        'SAHA_SMS_TEMPLATES_CONFIRMED':'0',
        'MELIPAYAMAK_OTP_CONTRACT_CONFIRMED':'1','SAHA_OTP_TTL_SECONDS':'120'}
    # Preserve an existing .env and its contents in a root-private backup folder.
    backup_environment(env)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',prefix='.sms-env-',dir=project,delete=False) as file:
            temporary=Path(file.name);os.chmod(file.name,0o600)
            file.write(updated_environment(text,values));file.flush();os.fsync(file.fileno())
        os.replace(temporary,env)
    finally:
        if temporary:temporary.unlink(missing_ok=True)
    print('کلیدها امن ثبت شدند و از تنظیمات قبلی بکاپ گرفته شد. ارسال در فایل تنظیمات خاموش است؛ هیچ سرویس یا دیتابیسی تغییر نکرد.')

if __name__=='__main__':main()
