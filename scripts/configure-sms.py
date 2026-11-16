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


def normalize_api_key(value):
    # Clipboard decoration is not part of an ASCII provider key. Never echo input.
    value=re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', value)
    value=value.replace('\x1b[200~','').replace('\x1b[201~','').strip()
    if not value:
        raise ValueError('هیچ متنی دریافت نشد؛ از گزینه Paste ترمیوس استفاده کنید.')
    if value.startswith('{'):
        try:data=json.loads(value)
        except ValueError:raise ValueError('متن JSON ناقص است؛ فقط آدرس کامل API را کپی کنید.') from None
        if not isinstance(data,dict):raise ValueError('فقط کلید یا آدرس کامل API لازم است.')
        candidates=[data[k] for k in ['MELIPAYAMAK_API_KEY','apiKey','api_key','key','url'] if k in data]
        if len(candidates)!=1 or not isinstance(candidates[0],str):
            raise ValueError('چند مقدار یا متن نامرتبط دریافت شد؛ فقط آدرس کامل API را کپی کنید.')
        value=candidates[0].strip()
    value=re.sub(r'^(?:MELIPAYAMAK_API_KEY|api[_ ]?key|url|آدرس\s*API|کلید\s*API)\s*[:=]\s*','',value,flags=re.I).strip()
    if value.startswith('"') and value.endswith('"'):
        try:decoded=json.loads(value)
        except ValueError:decoded=value[1:-1]
        if not isinstance(decoded,str):raise ValueError('فقط کلید یا آدرس لازم است.')
        value=decoded
    elif len(value)>=2 and (value[0],value[-1]) in [("'","'"),('`','`'),('«','»')]:
        value=value[1:-1]
    value=value.strip().replace('\\/', '/').replace('\\:', ':')
    markdown=re.fullmatch(r'\[[^\r\n]*\]\(([^\r\n]+)\)',value)
    if markdown:value=markdown[1].strip()
    if value.lower().startswith('console.melipayamak.com/'):
        value='https://'+value
    if '://' in value:
        url=urlsplit(value)
        if url.scheme.lower()!='https' or url.netloc.lower()!='console.melipayamak.com' or url.query or url.fragment:
            raise ValueError('آدرس باید HTTPS و متعلق به console.melipayamak.com باشد و بخش اضافی نداشته باشد.')
        match=re.fullmatch(r'/api/send/(?:otp|simple|shared|advanced|multiple)/\s*([A-Za-z0-9_-]{16,256})\s*/?',url.path)
        if not match:raise ValueError('آدرس کامل API شامل کلید لازم است؛ آدرس صفحه راهنما کافی نیست.')
        value=match[1]
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value):
        raise ValueError('متن دریافت‌شده قالب کلید API ندارد؛ فقط کلید یا آدرس کامل API را کپی کنید، نه نام کاربری یا رمز پنل.')
    return value


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
    for attempt in range(3):
        try:
            value=normalize_api_key(hidden_input())
            break
        except ValueError as error:
            print(str(error)+' چیزی ذخیره نشد.')
    else:
        raise SystemExit('ورود معتبر انجام نشد؛ هیچ تنظیماتی تغییر نکرد.')
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
