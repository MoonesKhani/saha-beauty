"""Transport protections without real networking."""
from dataclasses import replace
from unittest.mock import patch
from pydantic import SecretStr
import pytest
from backend.app.config import Settings
from backend.app.sms_provider import Melipayamak,NoRedirect,SmsUnavailable


def test_redirects_are_never_followed():
    assert NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.invalid') is None


def test_missing_keys_or_permission_cannot_reach_transport():
    calls=[]
    settings=Settings(sms_live_enabled=False,otp_contract_confirmed=True,melipayamak_api_key=SecretStr('offline-provider-key-fixture'))
    with pytest.raises(SmsUnavailable):Melipayamak(settings,lambda *args:calls.append(args)).send_otp('09123456789')
    with pytest.raises(SmsUnavailable):Melipayamak(replace(settings,sms_live_enabled=True,melipayamak_api_key=SecretStr('')),lambda *args:calls.append(args)).send_otp('09123456789')
    assert calls==[]


def test_secret_setup_preserves_existing_configuration_and_disables_sending():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('sms_setup',Path(__file__).resolve().parents[2]/'scripts/configure-sms.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='# keep comment\nPOSTGRES_PASSWORD=offline-fixture-db\nSAHA_OTP_ENABLED=1\nMELIPAYAMAK_API_KEY=old-fixture\nSAHA_OTP_ENABLED=1\n'
    result=module.updated_environment(text,{'SAHA_OTP_ENABLED':'0','MELIPAYAMAK_API_KEY':'new-offline-fixture'})
    assert '# keep comment\nPOSTGRES_PASSWORD=offline-fixture-db\n' in result
    assert result.count('SAHA_OTP_ENABLED=')==1 and 'SAHA_OTP_ENABLED=0' in result
    assert 'old-fixture' not in result
