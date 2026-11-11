from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get('DATABASE_URL', f'sqlite:///{ROOT / "var" / "saha.db"}'))
    admin_api_token: str = field(default_factory=lambda: os.environ.get('ADMIN_API_TOKEN', ''))
    frontend_dir: Path = field(default_factory=lambda: ROOT / 'frontend' / 'dist')
    preview_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_PREVIEW', '0') == '1')
    audio_upload_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_AUDIO_UPLOADS', '0') == '1')
    audio_upload_dir: Path = field(default_factory=lambda: Path(os.environ.get('SAHA_AUDIO_UPLOAD_DIR', str(ROOT / 'var' / 'audio-submissions'))))
    audio_upload_quota: int = field(default_factory=lambda: int(os.environ.get('SAHA_AUDIO_UPLOAD_QUOTA', str(250 * 1024 * 1024))))
    booking_enabled: bool = field(default_factory=lambda: os.environ.get('SAHA_BOOKING_ENABLED', '0') == '1')
