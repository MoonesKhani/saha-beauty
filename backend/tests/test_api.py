import json
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings, ROOT
from backend.app.cli import upgrade_database, seed_database
from backend.app.db import make_engine
from backend.app.models import Service
from backend.app.main import create_app
from frontend.build import build, render

# Fixture only; never used as an application credential or committed environment setting.
TEST_TOKEN = 'test-only-' + 'x' * 40

@pytest.fixture
def catalog_app(tmp_path):
    url = f'sqlite:///{tmp_path / "test.db"}'
    upgrade_database(url)
    seed_database(url)
    dist = build(tmp_path / 'frontend')
    settings = Settings(database_url=url, admin_api_token=TEST_TOKEN, frontend_dir=dist)
    with TestClient(create_app(settings)) as client:
        yield client, url, settings


def test_catalog_preserves_real_landing_data(catalog_app):
    client, _, _ = catalog_app
    expected = json.loads((ROOT / 'database/seed.json').read_text())
    response = client.get('/api/v1/catalog')
    assert response.status_code == 200
    data = response.json()
    assert len(data['services']) == len(expected['services']) and len(data['team']) == 7
    assert [(r['code'], r['name'], r['description']) for r in data['services']] == [(r['code'], r['name'], r['description']) for r in expected['services']]
    assert client.get('/health/ready').json() == {'status': 'ok', 'database': 'ready'}


def test_admin_auth_validation_persistence_and_stale_write(catalog_app):
    client, url, settings = catalog_app
    patch = {'revision': 1, 'description': 'توضیح آزمایشی'}
    assert client.patch('/api/v1/admin/services/01', json=patch).status_code == 401
    assert client.patch('/api/v1/admin/services/01', json=patch, headers={'Authorization': 'Bearer invalid'}).status_code == 401
    auth = {'Authorization': f'Bearer {TEST_TOKEN}'}
    assert client.patch('/api/v1/admin/services/01', json={'revision': 1, 'name': ' '}, headers=auth).status_code == 422
    assert client.patch('/api/v1/admin/services/01', json={**patch, 'unknown': 1}, headers=auth).status_code == 422
    assert client.patch('/api/v1/admin/services/99', json=patch, headers=auth).status_code == 404
    result = client.patch('/api/v1/admin/services/01', json=patch, headers=auth)
    assert result.status_code == 200 and result.json()['revision'] == 2
    assert client.patch('/api/v1/admin/services/01', json=patch, headers=auth).status_code == 409
    # Seeding and migration are repeatable and must not overwrite an owner's edits.
    upgrade_database(url)
    seed_database(url)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get('/api/v1/services/01').json()['description'] == 'توضیح آزمایشی'
        assert 'توضیح آزمایشی' in restarted.get('/').text


def test_bootstrap_cannot_break_out_of_script(catalog_app):
    client, _, _ = catalog_app
    text = '</script><script>window.attacked=1</script>'
    response = client.patch('/api/v1/admin/services/01', json={'revision': 1, 'name': text}, headers={'Authorization': f'Bearer {TEST_TOKEN}'})
    assert response.status_code == 200
    page = client.get('/')
    assert text not in page.text and '\\u003c/script\\u003e' in page.text
    assert page.headers['cache-control'] == 'no-store'
    assert client.get('/assets/saha-premium.css').status_code == 200
    assert client.get('/assets/../../.env').status_code in (404, 400)


def test_admin_disabled_by_default_and_no_health_data_endpoint(catalog_app):
    client, url, settings = catalog_app
    with TestClient(create_app(Settings(database_url=url, frontend_dir=settings.frontend_dir))) as locked:
        assert locked.patch('/api/v1/admin/services/01', json={'revision': 1, 'name': 'نمونه'}).status_code == 503
    assert client.post('/api/v1/bookings', json={'allergy': 'not-real-test'}).status_code == 404
    engine = make_engine(url)
    with engine.connect() as connection:
        from sqlalchemy import inspect
        assert set(inspect(connection).get_table_names()) == {'services', 'team_members', 'alembic_version','appointments','consultations','offers','staff_services','staff_schedules','appointment_services','booking_notices'}
    engine.dispose()


def test_readiness_requires_migrations(tmp_path):
    settings = Settings(database_url=f'sqlite:///{tmp_path / "uninitialized.db"}')
    with TestClient(create_app(settings)) as client:
        assert client.get('/health/ready').status_code == 503
        assert client.get('/api/v1/catalog').status_code == 503


def test_frontend_build_is_deterministic_and_preserves_design(tmp_path):
    first = build(tmp_path / 'dist')
    expected = render()
    assert (first / 'index.html').read_text() == expected
    build(first)
    assert (first / 'index.html').read_text() == expected
    for asset in (ROOT / 'assets').iterdir():
        if asset.is_file():
            assert (first / 'assets' / asset.name).read_bytes() == asset.read_bytes()
    # Static compatibility files and DNS config must stay untouched in this stage.
    assert (ROOT / 'CNAME').read_text().strip() == 'sahabeauty.ir'
