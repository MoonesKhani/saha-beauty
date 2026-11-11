from sqlalchemy import select
from .models import Service, TeamMember
from .schemas import CatalogOut

def read_catalog(session):
    return CatalogOut(
        services=list(session.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.sort_order, Service.code))),
        team=list(session.scalars(select(TeamMember).where(TeamMember.is_active.is_(True)).order_by(TeamMember.sort_order, TeamMember.code))),
    )
