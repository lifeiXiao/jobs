"""Runs only on GitHub-hosted Actions. Public, robots-aware, bounded collection."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT/'config/taxonomy.json').read_text(encoding='utf-8'))
TZ = dt.timezone(dt.timedelta(hours=8))
UA = 'JobsRadar/1.0 (+https://github.com/lifeiXiao/jobs)'
DATE_RE = re.compile(r'(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})日?')

def clean(text):
    return re.sub(r'[ \t\r\f\v]+', ' ', text).strip()

def read_text(node):
    copy=BeautifulSoup(str(node),'html.parser')
    for tag in copy.select('p,li,tr,h1,h2,h3,h4,h5,h6,div'):
        tag.append('\n')
    for tag in copy.select('br'): tag.replace_with('\n')
    return '\n'.join(clean(x) for x in copy.get_text(' ',strip=False).splitlines() if clean(x))

def dates(text):
    found=[]
    for m in DATE_RE.finditer(text):
        try: found.append((m, dt.date(*map(int,m.groups())).isoformat()))
        except ValueError: pass
    return found

def deadline(text):
    # Only dates explicitly tied to application windows qualify as deadlines.
    windows = re.findall(r'(?:报名(?:截止)?时间|报名期限|投递(?:截止)?时间|投递截止|报名截止|申请截止|应聘截止|简历接收截止|截止日期|截止时间|报名日期)[：:\s]*([^\n。；]{0,200})',text)
    for window in windows:
        ds=dates(window)
        if ds:
            m,end=ds[-1]
            after=window[m.end():]
            # A range ending in a year-less month/day inherits its explicit start year.
            rest=re.search(r'(?:至|到|—|~|～|－)\s*(\d{1,2})月(\d{1,2})日',after)
            if rest:
                try:
                    end=dt.date(int(end[:4]),int(rest[1]),int(rest[2])).isoformat()
                    after=after[rest.end():]
                except ValueError: continue
            # "报名时间：2026年11月1日起" only establishes a start, not an end.
            if len(ds)==1 and not rest and re.search(r'起|开始|启动',after) and not re.search(r'截止|截至',window):
                continue
            tm=re.search(r'(\d{1,2})\s*[:：时点]\s*(\d{1,2})?分?',after[:22])
            clock=None
            if tm and 0<=int(tm[1])<24 and int(tm[2] or 0)<60:
                clock=f'{int(tm[1]):02d}:{int(tm[2] or 0):02d}'
            return {'kind':'date','date':end,'time':clock,'label':end+((' '+clock) if clock else '（时刻未注明）'),'evidence':clean(window)[:230]}
    # "2026年11月30日截止" / "截至2026年11月30日" near application words.
    for line in text.splitlines():
        if re.search(r'报名|投递|简历|应聘|申请',line) and re.search(r'截止|截至|受理至|接收至',line):
            ds=dates(line)
            if ds:
                m,end=ds[-1]
                return {'kind':'date','date':end,'time':None,'label':end+'（时刻未注明）','evidence':clean(line)[:230]}
    for phrase in ['招满即止','招满为止','长期招聘','长期有效','常年招聘']:
        if phrase in text:
            return {'kind':'open','date':None,'time':None,'label':phrase,'evidence':phrase}
    return {'kind':'unknown','date':None,'time':None,'label':'原文未注明 · 请查看岗位表','evidence':None}

def classify(text, title=''):
    lines=text.splitlines()
    requirement_lines=[(' '.join(lines[i:i+3]) if len(line)<15 else line) for i,line in enumerate(lines) if re.search(r'专业|学科|研究方向|任职要求|岗位要求',line)]
    scope='\n'.join(requirement_lines) or title
    majors=[group for group,terms in TAXONOMY['majors'].items() if any(word in scope for word in terms)]
    return majors or ['专业待确认']

def cities(text,title=''):
    # A city in an institutional name is evidence, but footer/contact cities are not.
    location_lines=[line for line in text.splitlines() if re.search(r'工作(?:地[点址区]|城市)|招聘地点|岗位地点|任职地点|工作区域',line)]
    scope=' '.join(location_lines) if location_lines else title
    result=list(dict.fromkeys(c for c in TAXONOMY['cities'] if c in scope))
    if not result and re.search(r'全国|多地',scope): return ['全国 / 多地']
    return result or ['城市待确认']

def publication(soup,context):
    for query in ['meta[property="article:published_time"]','meta[name="pubdate"]','meta[name="publishdate"]','meta[name="PubDate"]']:
        tag=soup.select_one(query)
        if tag and dates(tag.get('content','')): return dates(tag['content'])[0][1]
    for line in read_text(soup).splitlines():
        if re.search(r'发布时间|发布日期|发表时间|更新日期',line) and dates(line): return dates(line)[0][1]
    ds=dates(context)
    return ds[0][1] if ds else None

def article(soup,selectors):
    for junk in soup.select('script,style,nav,header,footer,aside,noscript,.related,.recommend,.copyright'):
        junk.decompose()
    for selector in selectors+['article','main']:
        for node in soup.select(selector):
            if len(node.get_text(strip=True))>150: return node
    return soup.body or soup

def preview(text):
    lines=[clean(x) for x in text.splitlines() if len(clean(x))>8]
    requirement=[x for x in lines if re.search(r'专业|学历|学位|任职要求|岗位要求|工作地点|薪酬|薪资|报名时间',x)]
    # Short excerpts only; no wholesale republication of announcements.
    return '\n'.join(dict.fromkeys(requirement))[:700] or '\n'.join(lines[:4])[:450]

def positions(node):
    result=[]
    for table in node.select('table'):
        rows=table.select('tr')
        for index,tr in enumerate(rows[:5]):
            headers=[clean(c.get_text(' ',strip=True)) for c in tr.find_all(['th','td'])]
            role=next((i for i,h in enumerate(headers) if re.search(r'岗位名称|招聘岗位|职位名称',h)),None)
            major=next((i for i,h in enumerate(headers) if re.search(r'专业要求|所学专业|招聘专业|^专业$',h)),None)
            if role is None or major is None: continue
            for row in rows[index+1:]:
                cells=[clean(c.get_text(' ',strip=True)) for c in row.find_all(['td','th'])]
                # Merged cells need a real table model; keep such notices at announcement level.
                if len(cells)!=len(headers) or any(c.get('rowspan','1')!='1' for c in row.find_all(['td','th'])): continue
                if len(cells[role])<2 or len(cells[role])>100: continue
                context='\n'.join(f'{h}：{v}' for h,v in zip(headers,cells))
                if len(context)>25: result.append((cells[role],context))
            break
    return result[:40]

class SourceClient:
    def __init__(self):
        self.session=requests.Session(); self.session.headers['User-Agent']=UA
        self.robots={}; self.last={}
    def get(self,url):
        parsed=urlsplit(url)
        if parsed.scheme not in ('https','http'): raise ValueError('不支持的链接')
        origin=f'{parsed.scheme}://{parsed.netloc}'
        if origin not in self.robots:
            response=self.session.get(origin+'/robots.txt',timeout=(10,18))
            parser=RobotFileParser()
            if response.status_code==200:
                parser.parse(response.text.splitlines())
                self.robots[origin]=parser
            elif response.status_code in (404,410): self.robots[origin]=None
            else: raise RuntimeError(f'robots.txt 返回 {response.status_code}，暂停采集')
        parser=self.robots[origin]
        if parser is not None and not parser.can_fetch('JobsRadar',url): raise RuntimeError('robots.txt 不允许采集')
        delay=max(1.2,(parser.crawl_delay('JobsRadar') or parser.crawl_delay('*') or 0) if parser else 0)
        time.sleep(max(0,delay-(time.monotonic()-self.last.get(origin,0))))
        self.last[origin]=time.monotonic()
        response=self.session.get(url,timeout=(10,22))
        response.raise_for_status()
        if len(response.content)>4_000_000: raise RuntimeError('页面超出采集大小限制')
        if response.encoding in (None,'ISO-8859-1'): response.encoding=response.apparent_encoding
        text=response.text
        if re.search(r'验证码|访问验证|安全验证|Access Denied|Just a moment',text[:5000],re.I) and len(text)<20000:
            raise RuntimeError('来源需要人工验证，已跳过')
        return BeautifulSoup(text,'html.parser')

def canonical(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))

def collect_source(config,old,now):
    client=SourceClient(); output=[]; errors=[]; details_ok=0
    status={'id':config['id'],'name':config['name'],'category':config['category'],'url':config['url'],'checkedAt':now,'status':'error','count':0}
    try:
        soup=client.get(config['url']); found={}
        for a in soup.select('a[href]'):
            url=canonical(urljoin(config['url'],a['href']))
            title=clean(a.get('title') or a.get_text(' ',strip=True))
            if urlsplit(url).hostname!=urlsplit(config['url']).hostname: continue
            if not re.search(config['link_pattern'],url) or len(title)<8: continue
            if config.get('title_pattern') and not re.search(config['title_pattern'],title): continue
            if re.search(r'拟聘|录用公示|成绩|面试名单|考试大纲|笔试通知|取消.*岗位',title): continue
            parent=a.find_parent('tr') or a.find_parent('li') or a.parent
            if url not in found or len(title)>len(found[url][0]): found[url]=(title,clean(parent.get_text(' ',strip=True)))
        if not found: raise RuntimeError('未发现公告链接，来源页面可能已改版或需要登录')
        for url,(title,context) in list(found.items())[:config.get('limit',30)]:
            prior=old.get(url)
            if prior and prior.get('detailFetchedAt') and (dt.datetime.fromisoformat(now)-dt.datetime.fromisoformat(prior['detailFetchedAt'])).total_seconds()<6*86400:
                output.extend(prior['_siblings']); details_ok+=1; continue
            try:
                soup=client.get(url)
                pub=publication(soup,context)
                header_text='\n'.join(n.get_text(' ',strip=True) for n in soup.select('.detail-header,.detail-content,.detail-header-container'))
                node=article(soup,config.get('content_selectors',[]))
                text=read_text(node)
                if len(text)<80: raise RuntimeError('公告内容过短')
                due=deadline(text)
                if due['kind']=='unknown' and header_text: due=deadline(header_text)
                attachments=[]
                for a in node.select('a[href]'):
                    href=urljoin(url,a['href'])
                    if re.search(r'\.(?:xlsx?|pdf|docx?|zip)(?:\?|$)',href,re.I) and urlsplit(href).scheme in ('https','http'):
                        attachments.append({'name':clean(a.get_text(' ',strip=True)) or '岗位附件','url':href})
                base={'announcementTitle':title,'url':url,'sourceId':config['id'],'source':config['name'],'category':config['category'],'publishedAt':pub,'firstSeenAt':prior.get('firstSeenAt',now) if prior else now,'lastSeenAt':now,'detailFetchedAt':now,'deadline':due,'attachments':attachments[:8]}
                rows=positions(node)
                for i,(role,body) in enumerate(rows or [(title,text)]):
                    item={**base,'id':hashlib.sha256((url+'#'+str(i)+'#'+role).encode()).hexdigest()[:20],'title':role,'kind':'position' if rows else 'announcement','majors':classify(body,title),'cities':cities(body,title),'preview':preview(body),'degree':next((d for d in ['博士','硕士','本科','大专','专科','中专','高中'] if d in body),'原文未注明')}
                    if item['cities']==['城市待确认'] and config.get('default_cities'): item['cities']=config['default_cities']
                    if rows and deadline(body)['kind']!='unknown': item['deadline']=deadline(body)
                    item['salary']=next(iter(re.findall(r'[^\n。]{0,15}(?:薪资|薪酬|年薪|月薪)[^\n。]{0,65}',body)),'待遇见原文')
                    output.append(item)
                details_ok+=1
            except Exception as exc:
                errors.append(f'{title[:28]}：{str(exc)[:100]}')
                if prior: output.extend(prior['_siblings'])
        status.update(status='ok' if not errors else 'partial',count=len(output),discovered=len(found),detailsOk=details_ok,failedDetails=len(errors),message='已同步公开公告' if not errors else '部分详情读取失败，保留已有数据',errors=errors[:5])
    except Exception as exc:
        status['message']=str(exc)[:200]
    return output,status

def merge(previous,fresh,now):
    cutoff=(dt.datetime.fromisoformat(now)-dt.timedelta(days=120)).date().isoformat()
    merged={x['id']:x for x in previous}
    merged.update({x['id']:x for x in fresh})
    items=[x for x in merged.values() if (x.get('publishedAt') or x['firstSeenAt'][:10])>=cutoff]
    for x in items: x.pop('_siblings',None)
    return sorted(items,key=lambda x:(x.get('publishedAt') or '',x['firstSeenAt']),reverse=True)

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise SystemExit('采集仅允许在 GitHub 托管运行器执行；本机请运行离线测试。')
    now=dt.datetime.now(TZ).isoformat(timespec='seconds')
    path=ROOT/'data/jobs.json'
    previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'jobs':[],'sources':[]}
    grouped={}
    for x in previous['jobs']: grouped.setdefault(x['url'],[]).append(x)
    old={url:{**siblings[0],'_siblings':siblings} for url,siblings in grouped.items()}
    sources=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    fresh=[]; statuses=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures=[pool.submit(collect_source,c,old,now) for c in sources]
        for future in futures:
            jobs,status=future.result(); fresh.extend(jobs); statuses.append(status)
            print(f"{status['name']}: {status['status']} / {len(jobs)} / {status.get('message')}",flush=True)
    any_success=any(s['detailsOk']>0 for s in statuses if 'detailsOk' in s)
    result={'schemaVersion':1,'lastAttemptAt':now,'lastSuccessfulAt':now if any_success else previous.get('lastSuccessfulAt'),'schedule':'每天北京时间 08:23；失败后 14:23 重试','jobs':merge(previous['jobs'],fresh,now),'sources':statuses}
    path.parent.mkdir(exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write('# 招聘数据更新\n\n'+f'运行时间：{now}\n\n保留 {len(result["jobs"])} 条岗位 / 公告\n\n')
            for s in statuses: f.write(f'- {s["name"]}：{s["status"]} · {s["count"]} 条 · {s.get("message", "")}\n')
    if not any_success: raise SystemExit('所有来源读取失败；已保存诊断并保留上次数据。')

if __name__=='__main__': main()
