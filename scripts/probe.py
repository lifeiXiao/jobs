import concurrent.futures
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

SOURCES = [
 'https://www.zhaopin.com/sou/jl765/',
 'https://www.zhaopin.com/sou/jl635/',
 'https://www.zhaopin.com/jobdetail/CC120567060J40892154807.htm',
 'https://careers.tencent.com/tencentcareer/api/post/ByPostId?postId=2104502491390590976&language=zh-cn',
 'https://www.job5156.com/',
 'https://www.zhipin.com/c100010000/',
 'https://qzzyd.com/open/calendar',
]
def probe(url):
 out=[url]
 try:
  robots_url=urljoin(url,'/robots.txt')
  r=requests.get(robots_url, timeout=18)
  out.append(f'ROBOTS {r.status_code}: {r.text[:1800]}')
  if r.status_code == 200:
   p=RobotFileParser(); p.parse(r.text.splitlines())
   if not p.can_fetch('JobsRadar',url):
    return '\n'.join(out+['DISALLOWED'])
  elif r.status_code not in (404,410):
   return '\n'.join(out+['ROBOTS UNAVAILABLE'])
  r=requests.get(url,timeout=22,headers={'User-Agent':'JobsRadar/1.0 (+https://github.com/lifeiXiao/jobs)'})
  r.encoding=r.apparent_encoding
  out.append(f'PAGE {r.status_code} encoding={r.encoding} final={r.url}')
  out.append('SNIPPET '+r.text[:300])
  soup=BeautifulSoup(r.text,'html.parser')
  Path('snapshots').mkdir(exist_ok=True)
  Path('snapshots/'+url.replace('https://','').replace('/','_').replace('?','_')+'.html').write_text(r.text,encoding='utf-8')
  out.append('TITLE '+str(soup.title))
  selected=[a for a in soup.select('a[href]') if len(a.get_text(' ',strip=True))>12]
  for a in selected[:15]:
   out.append(str(a)[:250]+' PARENT '+a.parent.get_text(' ',strip=True)[:120])
 except Exception as e: out.append(str(e))
 return '\n'.join(out)
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
 for result in pool.map(probe,SOURCES): print(result+'\n---')
