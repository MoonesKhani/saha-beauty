from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
def render():return (ROOT/'index.html').read_text()
def build(output=None):
 target=Path(output) if output else ROOT/'frontend/dist'
 target.mkdir(parents=True,exist_ok=True)
 for name in ['index.html','ai-consultation.html','invite.html','gallery.html','discounts.html','booking.html','booking-demo.html','admin-access.html','playlist.html','scheduling.html','group-visit.html','admin-demo.html']:
  shutil.copy2(ROOT/name,target/name)
 shutil.copytree(ROOT/'assets',target/'assets',dirs_exist_ok=True)
 admin=(ROOT/'frontend/src/admin.html').read_text().replace('@@SAHA_DEMO_DATA@@','{}')
 (target/'admin.html').write_text(admin)
 leisure=(ROOT/'frontend/src/leisure.html').read_text().replace('@@SAHA_DEMO_DATA@@',(ROOT/'database/demo.json').read_text().replace('<','\\u003c'))
 (target/'leisure.html').write_text(leisure)
 return target
if __name__=='__main__':print(build())
