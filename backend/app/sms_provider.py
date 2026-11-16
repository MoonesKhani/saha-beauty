"""Only approved live requests can leave the server. Never log credential URLs or codes."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

class SmsUnavailable(RuntimeError):
    pass

class NotificationNotConfigured(SmsUnavailable):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a credential-bearing path to another host.

class Melipayamak:
    notifications_ready = False  # General/template API contract has not been supplied.

    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport or self._post

    @staticmethod
    def _post(url, body):
        request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={'Content-Type':'application/json'}, method='POST')
        # No HTTP client's URL debug logging; no environment proxy or redirects.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=8) as response:
                if response.status != 200:
                    raise SmsUnavailable('provider_unavailable')
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise SmsUnavailable('provider_invalid_response')
                return json.loads(raw)
        except (OSError, ValueError, urllib.error.URLError):
            raise SmsUnavailable('provider_unavailable') from None

    def send_otp(self, phone):
        key = self.settings.melipayamak_api_key.get_secret_value()
        if not (self.settings.sms_live_enabled and self.settings.otp_contract_confirmed
                and re.fullmatch(r'[A-Za-z0-9_-]{16,256}',key)):
            raise SmsUnavailable('provider_not_enabled')
        # Supplied documentation: generated code is returned only to this server.
        url = 'https://console.melipayamak.com/api/send/otp/' + urllib.parse.quote(key, safe='')
        try:
            data = self.transport(url, {'to':phone})
        except Exception:
            # Transport exceptions may contain the full credential URL. Never propagate them.
            raise SmsUnavailable('provider_unavailable') from None
        if not isinstance(data,dict) or data.get('status') not in (None,''):
            raise SmsUnavailable('provider_rejected')
        code = data.get('code')
        if not isinstance(code,str) or not re.fullmatch(r'[0-9]{4,10}',code):
            raise SmsUnavailable('provider_invalid_response')
        return code

    def send_notice(self, phone, kind, payload):
        # OTP endpoint cannot send appointment messages. No guessed endpoint/template.
        raise NotificationNotConfigured('notification_api_contract_required')
