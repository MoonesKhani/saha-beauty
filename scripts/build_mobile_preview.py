"""Create a standalone, unpublished visual preview with no dependency on CDN caches."""
from pathlib import Path
import argparse,base64,json,mimetypes,re
ROOT=Path(__file__).resolve().parents[1]
def data_url(path):
 mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
 return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
def inline_css(path):
 css=path.read_text()
 def replace(match):
  url=match[1].strip('"\' ')
  if url.startswith(('data:','http:','https:','#')):return match[0]
  asset=(path.parent/url).resolve()
  if not asset.is_relative_to(ROOT/'assets') or not asset.is_file():raise ValueError('Unknown local CSS asset: '+url)
  return 'url("'+data_url(asset)+'")'
 return re.sub(r'url\(([^)]+)\)',replace,css)
def inline_html(html):
 def style(match):return '<style>'+inline_css(ROOT/match[1].lstrip('./'))+'</style>'
 html=re.sub(r'<link rel="stylesheet" href="([^\"]+)"\s*/?>',style,html)
 def script(match):
  path=ROOT/match[2].lstrip('./')
  if not path.is_file():
   if re.fullmatch(r'[0-9a-f-]{36}',match[2]):return match[0]
   raise ValueError('Missing preview script: '+match[2])
  code=path.read_text()
  if path.name.startswith('saha-premium.') or path.name=='saha-premium.js':
   code=code.replace("const musicUrl = new URL('saha-quiet-bloom.mp3', document.currentScript.src).href;",'const musicUrl = '+json.dumps(data_url(ROOT/'assets/saha-quiet-bloom.mp3'))+';')
  if path.name=='saha-collections.js':code=code.replace("fetch('/assets/saha-gallery.json',{cache:'no-store'})","Promise.resolve({ok:true,json:async()=>[]})")
  if 'defer' in match[1]+match[3]:code="document.addEventListener('DOMContentLoaded',()=>{\n"+code+'\n});'
  return '<script>'+code.replace('</script','<\\/script')+'</script>'
 html=re.sub(r'<script([^>]*?)src="([^\"]+)"([^>]*)></script>',script,html)
 def image(match):
  path=ROOT/match[2].lstrip('./')
  return match[1]+'"'+data_url(path)+'"'
 return re.sub(r'((?:src|srcset)=)"(\./assets/[^\"]+)"',image,html)
def build(output):
 shell=(ROOT/'index.html').read_text();match=re.search(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)',shell,re.S)
 page=inline_html(json.loads(match[2]))
 child={name:inline_html((ROOT/name).read_text()) for name in ['gallery.html','discounts.html']}
 # Children are genuine separate Blob documents; their back link returns to this local preview.
 setup="""(() => {const home=location.href;const pages=@@PAGES@@;const routes={};for(const [name,html] of Object.entries(pages)){const doc=new DOMParser().parseFromString(html,'text/html');doc.querySelectorAll('a[href="/"]').forEach(a=>{a.setAttribute('href',home);a.setAttribute('onclick','event.preventDefault();history.back();');});routes['/'+name]=URL.createObjectURL(new Blob(['<!doctype html>'+doc.documentElement.outerHTML],{type:'text/html'}));}window.__sahaPreviewUnavailable=()=>alert('این فایل فقط پیش‌نمایش منتشرنشده چیدمان است؛ این بخش به سرور متصل نیست.');document.addEventListener('click',event=>{const link=event.target.closest?.('a');if(!link)return;const href=link.getAttribute('href');if(routes[href]){event.preventDefault();location.assign(routes[href]);return;}if(href?.startsWith('/')&&!href.startsWith('//')){event.preventDefault();window.__sahaPreviewUnavailable();}},true);})();""".replace('@@PAGES@@',json.dumps(child,ensure_ascii=False).replace('<','\\u003c'))
 page=page.replace('</body>','<script>'+setup+'</script></body>')
 for destination in ['/booking.html','/group-visit.html','/playlist.html']:
  page=page.replace('window.location.assign("'+destination+'")','window.__sahaPreviewUnavailable()').replace("window.location.assign('"+destination+"')",'window.__sahaPreviewUnavailable()')
 page=page.replace('<title>سها بیوتی | سالن زیبایی سها</title>','<title>پیش‌نمایش منتشرنشده موبایل | سها</title>')
 shell=shell[:match.start(2)]+json.dumps(page,ensure_ascii=False).replace('</','<\\u002F')+shell[match.end(2):]
 output.write_text(shell)
 return output
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/saha-mobile-v2-preview.html'));args=parser.parse_args();print(build(args.output))
