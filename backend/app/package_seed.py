"""Initial published requirements only; never overwrite owner edits or seed capacity."""
from sqlalchemy import select, func
from .models import Service,TeamMember,Package,StaffExpertise,StaffService

SERVICES = [('consultation','مشاوره'),('hand-rejuvenation','جوان‌سازی دست'),('manicure','مانیکور'),('pedicure','پدیکور'),('toe-gel','ژلیش پا'),('nail-gel','ژلیش ناخن'),('lens-lashes','لنز و مژه'),('decollete-facial','فشیال دکلته'),('facial','فشیال')]
BASIC=['consultation','04','hair-updo','11']
VIP=BASIC+['hand-rejuvenation','02','hair-color']
CIP=['consultation','04','lens-lashes','hair-updo','11','decollete-facial','hand-rejuvenation','02','pedicure','toe-gel','hair-color']
ENG=['04','hair-updo','11']
PACKAGES=[('bride-normal','عروس · عادی','bride','عادی',15000000,BASIC),('bride-vip','عروس · VIP','bride','VIP',25000000,VIP),('bride-cip','عروس · CIP','bride','CIP',45000000,CIP),('engagement-normal','عروس عقدی · عادی','engagement','عادی',8000000,ENG),('engagement-vip','عروس عقدی · VIP','engagement','VIP',15000000,ENG+['hand-rejuvenation','02']),('engagement-cip','عروس عقدی · CIP','engagement','CIP',23000000,ENG+['hand-rejuvenation','02','lens-lashes','facial']),('companion-normal','همراه عروس · عادی','companion','عادی',3000000,[]),('companion-vip','همراه عروس · VIP','companion','VIP',3500000,[]),('companion-cip','همراه عروس · CIP','companion','CIP',4000000,[]),('birthday','پکیج تولد','birthday','تولد',None,['hair-updo','04','02'])]

def seed_packages(db):
    order=(db.scalar(select(func.max(Service.sort_order))) or 0)+1
    for code,name in SERVICES:
        if db.get(Service,code) is None:
            db.add(Service(code=code,name=name,description=name,sort_order=order,price_toman=None));order+=1
    db.flush()
    order=(db.scalar(select(func.max(TeamMember.sort_order))) or 0)+1
    for code,name in [('assistant-narges','نرجس'),('assistant-sajedeh','ساجده')]:
        if not db.get(TeamMember,code):
            db.add(TeamMember(code=code,name=name,role='دستیار سهام شحیتی',bio='دستیار سهام شحیتی',parent_code='01',sort_order=order));order+=1
    db.flush()
    # Defaults are inserted once, alongside the initial packages. Re-running init-db
    # must not reinstate a specialty intentionally removed by the owner.
    first = db.get(Package,'bride-normal') is None
    if first:
        mapping={'01':['03','hair-braid','hair-updo','hair-scalp','hair-split-ends','hair-extensions','consultation'], '02':['02','07','manicure','pedicure','toe-gel','nail-gel'], '03':['04','lens-lashes'], '04':['hair-color'], '05':['08'], '06':['09'], '07':['11','05']}
        for staff,codes in mapping.items():
            if db.get(TeamMember,staff):
                for code in codes:
                    if db.get(Service,code) and not db.get(StaffExpertise,(staff,code)):db.add(StaffExpertise(staff_code=staff,service_code=code))
        # Correct old nail assignments; no duration or schedule is invented.
        from .packages import NAIL_CODES
        from sqlalchemy import delete
        db.execute(delete(StaffExpertise).where(StaffExpertise.service_code.in_(NAIL_CODES),StaffExpertise.staff_code!='02'))
        db.execute(delete(StaffService).where(StaffService.service_code.in_(NAIL_CODES),StaffService.staff_code!='02'))
    order=(db.scalar(select(func.max(Package.sort_order))) or 0)+1
    for code,name,category,tier,price,codes in PACKAGES:
        if not db.get(Package,code):
            db.add(Package(code=code,name=name,category=category,tier=tier,description='خدمات همراه عروس پس از تعریف در پنل مشخص می‌شود.' if category=='companion' else 'مدل مو یا رنگ متناسب با سلیقه‌ات؛ میکاپ مناسب جشن و عکس؛ طراحی ناخن با رنگ دلخواه؛ امکان آمدن با دوستان (مراجعه گروهی).' if category=='birthday' else name,price_toman=price,service_codes=codes,sort_order=order));order+=1
