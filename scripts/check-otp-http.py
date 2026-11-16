#!/usr/bin/env python3
"""Read-only public readiness check. GETs only; no credentials, sends or activation."""
import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

ROUTES=('/api/v1/health/ready','/api/v1/auth/capabilities','/api/openapi.json','/api/v1/booking/catalog')
OTP_METHODS={'/api/v1/auth/otp/request':'post','/api/v1/auth/otp/verify':'post','/api/v1/auth/me':'get'}
OTP_PATHS=tuple(OTP_METHODS)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def fetch_json(url):
    request=urllib.request.Request(url,headers={'Accept':'application/json','Cache-Control':'no-cache'},method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=10) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:return response.status,{}
            body=json.loads(raw)
            return response.status,body if isinstance(body,dict) else {}
    except urllib.error.HTTPError as error:
        status=error.code;error.close();return status,{}
    except (OSError,ValueError):return None,{}


def probe(base,fetch=fetch_json):
    parsed=urllib.parse.urlsplit(base)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Use only the HTTPS site origin, without credentials or an API key')
    responses={path:fetch(base.rstrip('/')+path) for path in ROUTES}
    health=responses[ROUTES[0]];capability=responses[ROUTES[1]];schema=responses[ROUTES[2]];booking=responses[ROUTES[3]]
    paths=schema[1].get('paths',{})
    if not isinstance(paths,dict):paths={}
    otp_routes=None if schema[0] is None else schema[0]==200 and all(isinstance(paths.get(path),dict) and method in paths[path] for path,method in OTP_METHODS.items())
    database=None if health[0] is None else health[0]==200 and health[1].get('database')=='ready'
    capability_valid=capability[0]==200 and type(capability[1].get('enabled')) is bool
    booking_valid=booking[0]==200 and type(booking[1].get('requires_login')) is bool
    report={'http_status':{path:item[0] for path,item in responses.items()},
        'database_ready':database,'otp_routes_available':otp_routes,
        'otp_enabled':capability[1]['enabled'] if capability_valid else None,
        'booking_requires_otp':booking[1]['requires_login'] if booking_valid else None,
        'ready_for_activation_review':database is True and otp_routes is True and capability_valid,
        'sms_sent':False}
    # Never return full response bodies or request headers.
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='https://sahabeauty.ir')
    args=parser.parse_args()
    try:print(json.dumps(probe(args.base_url),ensure_ascii=False,sort_keys=True))
    except ValueError:raise SystemExit('Only the HTTPS site origin is allowed; do not supply API credentials') from None
