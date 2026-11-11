"""Version the preview's changed assets together, without publishing anything."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
FILES=['saha-premium.css','saha-mobile-v2.css','saha-premium.js','saha-compact.js','saha-collections.css','saha-collections.js','saha-secondary.js','saha-trends.js']
PAGES=['index.html','gallery.html','discounts.html','ai-consultation.html','invite.html','daily.html','certificates.html','trends.html']
def build():
 versions={};counts={name:0 for name in FILES}
 for name in FILES:
  content=(ROOT/'assets'/name).read_bytes();stem,ext=name.rsplit('.',1)
  filename=f'{stem}.{hashlib.sha256(content).hexdigest()[:12]}.{ext}'
  (ROOT/'assets'/filename).write_bytes(content);versions[name]=filename
 for name in PAGES:
  path=ROOT/name;shell=path.read_text();match=re.search(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)',shell,re.S) if name=='index.html' else None
  text=json.loads(match[2]) if match else shell
  for asset,version in versions.items():
   stem,ext=asset.rsplit('.',1)
   pattern=r'((?:src|href)=")(\./assets/|/assets/)'+re.escape(stem)+r'(?:\.[a-f0-9]{12})?\.'+ext+r'(?:\?[^"\s]*)?(?=")'
   text,count=re.subn(pattern,lambda m:m[1]+m[2]+version,text);counts[asset]+=count
  path.write_text(shell[:match.start(2)]+json.dumps(text,ensure_ascii=False).replace('</','<\\u002F')+shell[match.end(2):] if match else text)
 if any(count==0 for count in counts.values()):raise ValueError('Unused versioned asset: '+str(counts))
 for asset,version in versions.items():
  stem,ext=asset.rsplit('.',1)
  for old in (ROOT/'assets').glob(stem+'.*.'+ext):
   if re.fullmatch(re.escape(stem)+r'\.[a-f0-9]{12}\.'+ext,old.name) and old.name!=version:old.unlink()
if __name__=='__main__':build()
