"""Distinguish missing deployment/routing from intentionally disabled OTP."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('otp_readiness',Path(__file__).resolve().parents[2]/'scripts/check-otp-http.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_mounted_but_disabled_is_not_a_missing_route():
    paths={path:{method:{}} for path,method in module.OTP_METHODS.items()}
    responses=dict(zip(module.ROUTES,[(200,{'database':'ready'}),(200,{'enabled':False}),(200,{'paths':paths}),(200,{'requires_login':False})]))
    calls=[]
    def get(url):
        path=url.removeprefix('https://site.invalid');calls.append(path)
        return responses[path]
    report=module.probe('https://site.invalid',get)
    assert calls==list(module.ROUTES)
    assert report['ready_for_activation_review'] is True and report['otp_enabled'] is False
    assert report['sms_sent'] is False


def test_healthy_old_app_with_missing_otp_is_not_ready():
    def get(url):return (200,{'database':'ready'}) if url.endswith('/health/ready') else (404,{})
    report=module.probe('https://site.invalid',get)
    assert report['database_ready'] is True and report['otp_routes_available'] is False
    assert report['ready_for_activation_review'] is False

@pytest.mark.parametrize('base',['http://site.invalid','https://user:private@site.invalid','https://site.invalid/api/send/otp/private','https://site.invalid?key=private'])
def test_credentials_or_api_urls_are_never_probed(base):
    with pytest.raises(ValueError):module.probe(base,lambda *_:pytest.fail('Network attempt'))


def test_network_failure_is_unknown_not_a_claim_of_database_outage():
    report=module.probe('https://site.invalid',lambda *_:(None,{}))
    assert report['database_ready'] is None and report['otp_enabled'] is None
    assert report['ready_for_activation_review'] is False
