"""Clipboard normalization only; no real key, server filesystem or network."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('sms_clipboard',Path(__file__).resolve().parents[2]/'scripts/configure-sms.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
KEY='offline-clipboard-key-fixture-0000'
URL='https://console.melipayamak.com/api/send/otp/'+KEY

@pytest.mark.parametrize('value',[
    KEY, URL, ' '+URL+' ', '"'+URL+'"', "'"+KEY+"'",
    '\u200f'+URL+'\u200e', '\x1b[200~'+URL+'\x1b[201~',
    'MELIPAYAMAK_API_KEY='+KEY, 'API Key: '+KEY, 'کلید API: '+KEY,
    '{"apiKey":"'+KEY+'"}', '"'+URL.replace('/','\\/')+'"',
    URL+'/', URL.removeprefix('https://'), URL.replace('/otp/','/simple/'),
    '[آدرس API]('+URL+')', URL.replace('/otp/','/otp/ '),
])
def test_clipboard_wrappers_preserve_the_exact_key(value):
    assert module.normalize_api_key(value)==KEY

@pytest.mark.parametrize('value',[
    '', '   ', 'short-password', 'https://console.melipayamak.com/send/otp',
    'https://other.invalid/api/send/otp/'+KEY,
    'https://console.melipayamak.com.evil.invalid/api/send/otp/'+KEY,
    'https://console.melipayamak.com@other.invalid/api/send/otp/'+KEY,
    URL+'?extra=1', URL+'#fragment', 'http://console.melipayamak.com/api/send/otp/'+KEY,
    'part of '+KEY, '{"key":"'+KEY+'","url":"'+URL+'"}',
])
def test_invalid_input_has_safe_diagnostics(value):
    with pytest.raises(ValueError) as error:module.normalize_api_key(value)
    assert KEY not in str(error.value) and URL not in str(error.value)
