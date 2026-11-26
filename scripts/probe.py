import concurrent.futures
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

SOURCES = [
 'https://www.zhipin.com/web/geek/jobs?city=100010000',
 'https://sou.zhaopin.com/',
 'https://careers.tencent.com/tencentcareer/api/post/Query?pageIndex=1&pageSize=20&language=zh-cn&area=cn',
 'https://www2.iguopin.com/',
 'https://www.jobui.com/jobs/',
 'https://jobs.51job.com/',
 'https://www.liepin.com/zhaopin/',
 'https://hr.163.com/job-list.html',
 'https://jobs.bytedance.com/experienced/position',
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
  out.append(f'PAGE {r.status_code} encoding={r.encoding}')
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
