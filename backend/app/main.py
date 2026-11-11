from contextlib import asynccontextmanager
import secrets
import re
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .config import Settings, ROOT
from .db import make_engine
from .models import Service
from .schemas import CatalogOut, ServiceOut, ServicePatch
from .catalog import read_catalog

bearer = HTTPBearer(auto_error=False)

def create_app(settings=None):
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_):
        yield
        engine.dispose()

    app = FastAPI(title='رابط برنامه‌نویسی سها', version='0.1.0', docs_url='/api/docs', lifespan=lifespan)
    app.state.engine = engine

    @app.middleware('http')
    async def private_cache_policy(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(('/admin','/api/v1/admin')):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def session():
        with Session(engine) as db:
            yield db

    def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if len(settings.admin_api_token) < 32:
            raise HTTPException(503, 'دسترسی مدیریت هنوز پیکربندی نشده است.')
        if credentials is None or not secrets.compare_digest(credentials.credentials.encode(), settings.admin_api_token.encode()):
            raise HTTPException(401, 'دسترسی مجاز نیست.', headers={'WWW-Authenticate': 'Bearer'})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_, __):
        return JSONResponse(status_code=503, content={'detail': 'پایگاه داده آماده نیست.'})

    @app.get('/health/ready')
    def ready():
        try:
            with engine.connect() as connection:
                version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                if version != '0003_booking':
                    raise HTTPException(503, 'نسخه پایگاه داده آماده نیست.')
            return {'status': 'ok', 'database': 'ready'}
        except SQLAlchemyError:
            raise HTTPException(503, 'پایگاه داده آماده نیست.') from None

    @app.get('/api/v1/catalog', response_model=CatalogOut)
    def catalog(db: Session = Depends(session)):
        return read_catalog(db)

    @app.get('/api/v1/services/{code}', response_model=ServiceOut)
    def service(code: str, db: Session = Depends(session)):
        record = db.get(Service, code)
        if record is None:
            raise HTTPException(404, 'خدمت پیدا نشد.')
        return record

    @app.patch('/api/v1/admin/services/{code}', response_model=ServiceOut, dependencies=[Depends(require_admin)])
    def edit_service(code: str, patch: ServicePatch, db: Session = Depends(session)):
        if db.get(Service, code) is None:
            raise HTTPException(404, 'خدمت پیدا نشد.')
        changes = patch.model_dump(exclude={'revision'}, exclude_unset=True)
        changes = {k:v for k,v in changes.items() if v is not None or k=='price_toman'}
        result = db.execute(update(Service).where(Service.code == code, Service.revision == patch.revision).values(**changes, revision=patch.revision + 1))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, 'اطلاعات تغییر کرده است؛ نسخه تازه را دریافت کنید.')
        db.commit()
        db.expire_all()
        return db.get(Service, code)

    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def landing(db: Session = Depends(session)):
        path = settings.frontend_dir / 'index.html'
        if not path.is_file():
            raise HTTPException(503, 'ابتدا فرانت‌اند را بسازید: python3 frontend/build.py')
        payload = read_catalog(db).model_dump_json()
        for char, escaped in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
            payload = payload.replace(char, escaped)
        bootstrap = '<script>window.__SAHA_CATALOG__=' + payload + ';' + ('window.__SAHA_PREVIEW__=true;' if settings.preview_enabled else '') + '</script>'
        html = path.read_text().replace('<head>', '<head>' + bootstrap, 1)
        return HTMLResponse(html, headers={'Cache-Control': 'no-store'})

    from .audio_uploads import mount_audio_uploads
    mount_audio_uploads(app, settings, require_admin)

    from .booking import mount_booking
    mount_booking(app, settings, session, require_admin)

    from .management import mount_management
    mount_management(app, session, require_admin)

    @app.get('/admin', response_class=HTMLResponse, include_in_schema=False)
    def admin_page():
        html=(settings.frontend_dir / 'admin.html').read_text().replace('@@SAHA_MODE@@','live')
        html=re.sub(r'(<script id="saha-demo-data" type="application/json">).*?(</script>)',r'\g<1>{}\g<2>',html,flags=re.S)
        return HTMLResponse(html,headers={'Cache-Control':'no-store'})

    @app.get('/admin/demo', response_class=HTMLResponse, include_in_schema=False)
    def demo_page():
        if not settings.preview_enabled:
            raise HTTPException(404, 'صفحه پیدا نشد.')
        return HTMLResponse((settings.frontend_dir / 'admin-demo.html').read_text(), headers={'Cache-Control':'no-store'})

    @app.get('/playlist.html', response_class=HTMLResponse, include_in_schema=False)
    def customer_playlist():
        return HTMLResponse((settings.frontend_dir / 'playlist.html').read_text())

    @app.get('/{page}', response_class=HTMLResponse, include_in_schema=False)
    def leisure_page(page: str, demo: bool=False):
        if page in ['booking.html','booking-demo.html','admin-access.html','scheduling.html','admin-demo.html','group-visit.html','playlist.html']:
            return HTMLResponse((settings.frontend_dir / page).read_text(),headers={'Cache-Control':'no-store'})
        if (demo and not settings.preview_enabled) or page not in ['buffet','playlist','products']:
            raise HTTPException(404,'صفحه پیدا نشد.')
        html=(settings.frontend_dir / 'leisure.html').read_text().replace('@@SAHA_KIND@@',page).replace('@@SAHA_MODE@@','demo' if demo else 'live')
        if not demo:html=re.sub(r'(<script id="saha-demo-data" type="application/json">).*?(</script>)',r'\g<1>{}\g<2>',html,flags=re.S)
        return HTMLResponse(html,headers={'Cache-Control':'no-store'})

    app.mount('/assets', StaticFiles(directory=settings.frontend_dir / 'assets', check_dir=False), name='assets')
    return app

app = create_app()
