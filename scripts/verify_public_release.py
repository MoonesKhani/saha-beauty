"""Check the release identity actually visible through the public CDN/domain."""
import argparse,json,re,time,urllib.request,urllib.parse
from uuid import uuid4

def verify(image,url,attempts=30,delay=5):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):raise ValueError('Invalid release image identity')
    if not url.startswith('https://'):raise ValueError('Public verification requires HTTPS')
    for _ in range(attempts):
        try:
            target=url.rstrip('/')+'/release.json?'+urllib.parse.urlencode({'image':image,'check':uuid4().hex})
            request=urllib.request.Request(target,headers={'Cache-Control':'no-cache'})
            with urllib.request.urlopen(request,timeout=10) as response:
                if json.load(response).get('image_id')==image:
                    print('Public site matches approved image '+image);return
        except Exception:pass
        time.sleep(delay)
    raise RuntimeError('Public site/CDN does not show the expected release; rollback is required')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--url',default='https://sahabeauty.ir');a=p.parse_args();verify(a.image,a.url)
