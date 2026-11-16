from dataclasses import dataclass, field
from pathlib import Path
import os
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get('DATABASE_URL', f'sqlite:///{ROOT / "var" / "saha.db"}'))
    # Server-only credentials; sending is disabled unless explicitly enabled.
    melipayamak_api_key: SecretStr = field(default_factory=lambda: SecretStr(os.environ.get('MELIPAYAMAK_API_KEY', '')), repr=False)
    otp_secret: SecretStr = field(default_factory=lambda: SecretStr(os.environ.get('SAHA_OTP_SECRET', '')), repr=False)
    otp_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_OTP_ENABLED', '0') == '1')
    sms_live_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_SMS_LIVE_ENABLED', '0') == '1')
    otp_contract_confirmed: bool = field(default_factory=lambda: os.environ.get('MELIPAYAMAK_OTP_CONTRACT_CONFIRMED', '0') == '1')
    otp_ttl_seconds: int = field(default_factory=lambda: int(os.environ.get('SAHA_OTP_TTL_SECONDS', '120')))
    sms_notifications_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_SMS_NOTIFICATIONS_ENABLED', '0') == '1')
    sms_templates_confirmed: bool = field(default_factory=lambda: os.environ.get('SAHA_SMS_TEMPLATES_CONFIRMED', '0') == '1')
    sms_booking_body_id: int = field(default_factory=lambda: int(os.environ.get('MELIPAYAMAK_BOOKING_BODY_ID', '0')))
    sms_repair_body_id: int = field(default_factory=lambda: int(os.environ.get('MELIPAYAMAK_REPAIR_BODY_ID', '0')))
    admin_api_token: str = field(default_factory=lambda: os.environ.get('ADMIN_API_TOKEN', ''))
    frontend_dir: Path = field(default_factory=lambda: ROOT / 'frontend' / 'dist')
    preview_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_PREVIEW', '0') == '1')
    audio_upload_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_AUDIO_UPLOADS', '0') == '1')
    audio_upload_dir: Path = field(default_factory=lambda: Path(os.environ.get('SAHA_AUDIO_UPLOAD_DIR', str(ROOT / 'var' / 'audio-submissions'))))
    audio_upload_quota: int = field(default_factory=lambda: int(os.environ.get('SAHA_AUDIO_UPLOAD_QUOTA', str(250 * 1024 * 1024))))
    booking_require_otp: bool = field(default_factory=lambda: os.environ.get('SAHA_BOOKING_REQUIRE_OTP', '0') == '1')
    booking_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_BOOKING_ENABLED', '0') == '1')
    gallery_upload_dir: Path = field(default_factory=lambda: Path(os.environ.get('SAHA_GALLERY_UPLOAD_DIR', str(ROOT / 'var' / 'gallery'))))
    gallery_upload_quota: int = field(default_factory=lambda: int(os.environ.get('SAHA_GALLERY_UPLOAD_QUOTA', str(250 * 1024 * 1024))))
