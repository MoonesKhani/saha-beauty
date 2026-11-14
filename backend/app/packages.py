"""Owner-controlled packages and a shared, server-authoritative price calculation."""
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .models import Package, Service, GalleryImage, StaffExpertise
from .management import Input, out

NAIL_CODES = {'02', '07', 'manicure', 'pedicure', 'toe-gel', 'nail-gel'}
def eligible_staff(db, staff_code, service_code):
    if service_code in NAIL_CODES and staff_code != '02':
        return False
    return db.get(StaffExpertise, (staff_code, service_code)) is not None

class QuoteInput(Input):
    package_code: str = Field(min_length=1, max_length=36)
    service_codes: list[str] = Field(max_length=30)

def quote_package(db, code, codes):
    package = db.get(Package, code)
    if not package or not package.is_active:
        raise HTTPException(422, 'پکیج فعال انتخاب کنید.')
    if len(codes) != len(set(codes)):
        raise HTTPException(422, 'خدمت تکراری است.')
    selected, included = set(codes), set(package.service_codes)
    all_codes = selected | included
    services = {s.code:s for s in db.scalars(select(Service).where(Service.code.in_(all_codes)))}
    if any(c not in services or not services[c].is_active for c in selected):
        raise HTTPException(422, 'خدمت فعال انتخاب کنید.')
    changed = (selected ^ included) if package.price_toman is not None else selected
    missing = sorted(c for c in changed if c not in services or services[c].price_toman is None)
    # An unconfigured companion package must never imply any unspecified services.
    configured = bool(included)
    price = None
    if configured and selected and not missing:
        if package.price_toman is None:
            price = sum(services[c].price_toman for c in selected)
        else:
            price = package.price_toman + sum(services[c].price_toman for c in selected-included) - sum(services[c].price_toman for c in included-selected)
            if price < 0:
                raise HTTPException(422, 'تعرفه خدمات با قیمت پکیج سازگار نیست؛ با سالن هماهنگ کنید.')
    result = {'package_code':code, 'package_revision':package.revision, 'service_codes':sorted(selected),
            'base_price_toman':package.price_toman, 'total_toman':price,
            'missing_prices':missing, 'configured':configured,
            'tariffs':{c:{'price_toman':services[c].price_toman,'revision':services[c].revision} for c in sorted(all_codes) if c in services},
            'message': 'خدمات این پکیج هنوز از پنل تعریف نشده است.' if not configured else 'تعرفه برخی خدمات مشخص نشده است.' if missing else 'قیمت محاسبه شد.' if price is not None else 'خدمتی انتخاب نشده است.'}

    import hashlib, json
    result['quote_version']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result

def mount_packages(app, session):
    @app.get('/api/v1/packages')
    def packages(db=Depends(session)):
        return {'items':[out(p) for p in db.scalars(select(Package).where(Package.is_active.is_(True)).order_by(Package.sort_order))]}
    @app.post('/api/v1/packages/quote')
    def quote(data:QuoteInput, db=Depends(session)):
        return quote_package(db, data.package_code, data.service_codes)
    @app.get('/api/v1/gallery')
    def gallery(db=Depends(session)):
        return {'items':[out(p) for p in db.scalars(select(GalleryImage).where(GalleryImage.is_active.is_(True)).order_by(GalleryImage.id))]}
