"""Fingerprint the landing CSS/JS together so cached legacy assets cannot be mixed in."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
FILES=['saha-premium.css','saha-mobile-v2.css','saha-premium.js','saha-compact.js']
def build():
 path=ROOT/'index.html';shell=path.read_text();match=re.search(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)',shell,re.S)
 page=json.loads(match[2])
 for name in FILES:
  source=ROOT/'assets'/name;content=source.read_bytes();version=hashlib.sha256(content).hexdigest()[:12];stem,ext=name.rsplit('.',1);filename=f'{stem}.{version}.{ext}'
  # Keep the closing quote in place and match both the initial and already-versioned URL.
  pattern=r'((?:src|href)=")\./assets/'+re.escape(stem)+r'(?:\.[a-f0-9]{12})?\.'+ext+r'(?:\?[^"\s]*)?(?=")'
  page,count=re.subn(pattern,lambda m:m[1]+'./assets/'+filename,page)
  if count!=1:raise ValueError(f'Expected one landing reference for {name}, got {count}')
  (ROOT/'assets'/filename).write_bytes(content)
  for old in (ROOT/'assets').glob(stem+'.*.'+ext):
   if re.fullmatch(re.escape(stem)+r'\.[a-f0-9]{12}\.'+ext,old.name) and old.name!=filename:old.unlink()
 shell=shell[:match.start(2)]+json.dumps(page,ensure_ascii=False).replace('</','<\\u002F')+shell[match.end(2):]
 path.write_text(shell)
if __name__=='__main__':build()
