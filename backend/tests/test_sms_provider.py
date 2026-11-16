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

def test_service_line_contract_and_acceptance_receipt():
    calls=[]
    settings=Settings(sms_live_enabled=True,sms_notifications_enabled=True,sms_templates_confirmed=True,
        sms_booking_body_id=123,sms_repair_body_id=456,melipayamak_api_key=SecretStr('offline-provider-key-fixture'))
    def transport(url,body):
        calls.append((url,body));return {'recId':3741437414,'status':''}
    provider=Melipayamak(settings,transport)
    assert provider.send_notice('09123456789','booking_confirmation',{'starts_at':'2026-11-20T12:00+03:30','appointment_reference':'offline-reference'})=='3741437414'
    assert calls[0]==('https://console.melipayamak.com/api/send/shared/offline-provider-key-fixture',{'bodyId':123,'to':'09123456789','args':['2026-11-20T12:00+03:30','offline-reference']})
    provider.send_notice('09123456789','repair_reminder',{'appointment_reference':'offline-reference'})
    assert calls[1][1]=={'bodyId':456,'to':'09123456789','args':['offline-reference']}
    with pytest.raises(SmsUnavailable):
        Melipayamak(replace(settings,sms_templates_confirmed=False),lambda *_:pytest.fail('real send')).send_notice('09123456789','repair_reminder',{})


@pytest.mark.parametrize('data',[{'recId':-1},{'recId':True},{'recId':123,'status':'error'},{'code':'123456'}])
def test_service_line_rejects_missing_or_invalid_receipt(data):
    settings=Settings(sms_live_enabled=True,sms_notifications_enabled=True,sms_templates_confirmed=True,
        sms_booking_body_id=123,sms_repair_body_id=456,melipayamak_api_key=SecretStr('offline-provider-key-fixture'))
    with pytest.raises(SmsUnavailable):
        Melipayamak(settings,lambda *_:data).send_notice('09123456789','repair_reminder',{'appointment_reference':'fixture'})

def test_scheduler_selects_only_the_existing_project_app(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('sms_runner',Path(__file__).resolve().parents[2]/'scripts/run-sms-worker.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    good={'Id':'offline-existing-app','State':{'Running':True},'Config':{'Labels':{'com.docker.compose.project.working_dir':str(tmp_path),'com.docker.compose.oneoff':'False'}}}
    unrelated={'Id':'other-app','State':{'Running':True},'Config':{'Labels':{'com.docker.compose.project.working_dir':'/different'}}}
    assert module.choose_app([good,unrelated],tmp_path)=='offline-existing-app'
    with pytest.raises(ValueError):module.choose_app([unrelated],tmp_path)
    with pytest.raises(ValueError):module.choose_app([good,good],tmp_path)

def test_secret_prompt_never_falls_back_to_visible_input(tmp_path):
    import importlib.util
    import getpass
    import warnings
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('sms_setup_hidden',Path(__file__).resolve().parents[2]/'scripts/configure-sms.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def unavailable(*_):warnings.warn('No secure terminal',getpass.GetPassWarning)
    with patch.object(module.getpass,'getpass',side_effect=unavailable):
        with pytest.raises(SystemExit):module.hidden_input()
    checkout=tmp_path/'checkout';checkout.mkdir();env=checkout/'.env';env.write_text('OFFLINE_FIXTURE_ONLY=1\n')
    backup=module.backup_environment(env,tmp_path/'private')
    assert not backup.is_relative_to(checkout)
    assert (backup/'environment').read_bytes()==env.read_bytes()
    assert (backup.stat().st_mode & 0o777)==0o700
    assert ((backup/'environment').stat().st_mode & 0o777)==0o600
