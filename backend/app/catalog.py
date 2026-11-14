from sqlalchemy import select
from .models import Service, TeamMember, Package, GalleryImage
from .schemas import CatalogOut

def read_catalog(session):
    from .management import out
    return CatalogOut(
        packages=[out(p) for p in session.scalars(select(Package).where(Package.is_active.is_(True)).order_by(Package.sort_order))],
        gallery=[out(p) for p in session.scalars(select(GalleryImage).where(GalleryImage.is_active.is_(True)).order_by(GalleryImage.id))],
        services=list(session.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.sort_order, Service.code))),
        team=list(session.scalars(select(TeamMember).where(TeamMember.is_active.is_(True)).order_by(TeamMember.sort_order, TeamMember.code))),
    )
