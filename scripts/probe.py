import concurrent.futures
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

SOURCES = [
 'https://www.yingjiesheng.com/other/',
 'https://www.yingjiesheng.com/commend/',
 'https://www.shiyebian.net/zhaopin/',
 'https://www.gaoxiaojob.com/announcement/',
 'https://yjsb.zafu.edu.cn/xxfw/jyxx.htm',
 'https://www.mohrss.gov.cn/SYrlzyhshbzb/fwyd/SYkaoshizhaopin/zyhgjjgsydwgkzp/zpgg/index.html',
 'https://jshrss.jiangsu.gov.cn/col/col57210/index.html',
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
  soup=BeautifulSoup(r.text,'html.parser')
  out.append('TITLE '+str(soup.title))
  selected=[a for a in soup.select('a[href]') if len(a.get_text(' ',strip=True))>12]
  for a in selected[:35]:
   out.append(str(a)[:500]+' PARENT '+a.parent.get_text(' ',strip=True)[:350])
 except Exception as e: out.append(str(e))
 return '\n'.join(out)
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
 for result in pool.map(probe,SOURCES): print(result+'\n---')
