"""Public enterprise listings and conservative, provenance-preserving deduplication."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import urljoin,urlsplit,parse_qs,urlencode,urlunsplit
from bs4 import BeautifulSoup
from collect import SourceClient,clean,read_text,dates,deadline,classify,cities,PARSER_VERSION

def initial_state(soup):
    for script in soup.select('script'):
        text=script.get_text()
        m=re.search(r'(?:window\.)?__INITIAL_STATE__\s*=\s*',text)
        if m:
            try:return json.JSONDecoder().raw_decode(text[m.end():])[0]
            except (ValueError,TypeError):pass
    return {}

def day(value):
    ds=dates(str(value or ''))
    return ds[0][1] if ds else None

def normalize(config,old,now,*,title,url,company='',body='',location='',salary='',degree='',experience='',industry='',published=None,updated=None,due=None,category=None,original_url=None):
    prior=old.get(url,{})
    category=category or ('实习' if '实习' in title else '企业校招' if re.search(r'校招|校园招聘|应届',title) else '企业社招')
    major=classify(body,title)
    if major==['专业待确认']:major=classify('',title)
    city=cities('工作地点：'+location) if location else cities('',title)
    return {'parserVersion':PARSER_VERSION,'id':hashlib.sha256(('enterprise:'+url).encode()).hexdigest()[:20],'kind':'position','title':clean(title),'announcementTitle':clean(title),'company':clean(company),'industry':industry,'employmentType':category,'experience':experience or '经验见原文','url':url,'originalUrl':original_url or url,'sourceId':config['id'],'source':config['name'],'category':category,'publishedAt':day(published),'updatedAt':day(updated),'firstSeenAt':prior.get('firstSeenAt',now),'lastSeenAt':now,'detailFetchedAt':now,'deadline':due or deadline(body),'attachments':[],'majors':major,'cities':city,'preview':body[:900] or '公开页面暂未提供职位描述，请查看原始岗位。','degree':degree or next((d for d in ['博士','硕士','本科','大专','专科','中专','高中'] if d in body),'原文未注明'),'salary':salary or '原文未公开薪资','previewKind':'公开岗位摘录'}

def collect_zhaopin(config,client,old,now,errors):
    records={}
    for url in config.get('list_urls',[config['url']]):
        try:
            soup=client.get(url);state=initial_state(soup)
            rows=state.get('positionList') or []
            if not rows:raise ValueError('公开列表没有岗位数据')
            for row in rows:
                pos=(row.get('jobDetailData') or {}).get('position') or {}
                base=pos.get('base') or {};description=pos.get('desc') or {};timing=pos.get('date') or {}
                joburl=row.get('positionUrl') or row.get('positionURL')
                title=row.get('name') or base.get('positionName')
                if not joburl or not title:continue
                card=next((a.find_parent(class_='job-card') for a in soup.select('a[href]') if a.get('href')==joburl),None)
                body=read_text(BeautifulSoup(description.get('description') or '','html.parser'))
                if not body and card:
                    node=card.select_one('.job-card__seo-description');body=node.get_text(' ',strip=True) if node else ''
                visible_salary=card.select_one('.job-card__salary') if card else None
                salary=visible_salary.get_text(' ',strip=True) if visible_salary else ''
                if '*' in salary:salary='平台未公开薪资 · 请查看原文'
                date_end=timing.get('dateEnd')
                due=deadline('报名截止日期：'+date_end) if day(date_end) else deadline(body)
                records[joburl]=normalize(config,old,now,title=title,url=joburl,company=row.get('companyName',''),body=body,location=row.get('workCity',''),salary=salary,degree=row.get('education') or base.get('education'),experience=row.get('workingExp',''),industry=row.get('industryName',''),published=row.get('publishTime') or timing.get('positionPublishTime'),updated=timing.get('positionUpdateTime'),due=due)
        except Exception as exc:errors.append(f'{url}：{str(exc)[:100]}')
    return list(records.values())

def collect_tencent(config,client,old,now,errors):
    records=[];detail_count=0
    for page in range(1,config.get('pages',5)+1):
        endpoint='https://careers.tencent.com/tencentcareer/api/post/Query?'+urlencode({'pageIndex':page,'pageSize':100,'language':'zh-cn','area':'cn'})
        try:
            payload=client.json(endpoint)
            if payload.get('Code')!=200:raise ValueError('公开接口未返回成功状态')
            rows=(payload.get('Data') or {}).get('Posts') or []
            if not rows:break
            for row in rows:
                if not row.get('IsValid',True) or row.get('CountryName') not in ('中国','中国大陆',''):continue
                joburl='https://careers.tencent.com/jobdesc.html?postId='+str(row['PostId'])
                body=row.get('Responsibility') or ''
                requirements='';degree=''
                if detail_count<config.get('detail_limit',60):
                    try:
                        detail=client.json('https://careers.tencent.com/tencentcareer/api/post/ByPostId?'+urlencode({'postId':row['PostId'],'language':'zh-cn'})).get('Data') or {}
                        requirements=detail.get('Requirement') or '';body=detail.get('Responsibility') or body
                        detail_count+=1
                    except Exception as exc:errors.append('岗位详情补充失败：'+str(exc)[:80])
                body=read_text(BeautifulSoup('岗位职责：\n'+body+'\n任职要求：\n'+requirements,'html.parser'))
                records.append(normalize(config,old,now,title=row['RecruitPostName'],url=joburl,company=row.get('ComName') or '腾讯',body=body,location=row.get('LocationName',''),industry=row.get('CategoryName',''),experience=row.get('RequireWorkYearsName',''),updated=row.get('LastUpdateTime')))
        except Exception as exc:
            errors.append(str(exc)[:140]);break
    return records

def collect_job5156(config,client,old,now,errors):
    records={}
    for entry in config.get('list_urls',[config['url']]):
        try:
            soup=client.get(entry)
            for anchor in soup.select('a[href*="/job_"]'):
                url=urljoin(entry,anchor['href'])
                if url in records:continue
                container=anchor.find_parent(class_='home-hot-job-item') or anchor.find_parent(class_='job_only_box')
                if container is None:continue
                card=container.select_one('.job_card')
                if not card:continue
                def text(selector):
                    node=container.select_one(selector)
                    return node.get_text(' ',strip=True) if node else ''
                title=text('.job-card_posName a') or anchor.get_text(' ',strip=True)
                records[url]=normalize(config,old,now,title=title,url=url,company=text('.com_name'),body=text('.job-card_message'),location=text('.job-card_site'),salary=text('.job-card_posName span'),degree=text('.job-card_degreeStr'))
        except Exception as exc:errors.append(str(exc)[:150])
    return list(records.values())

def collect_public_table(config,client,old,now,errors):
    soup=client.get(config['url']);records=[]
    for tr in soup.select('tbody tr')[:config.get('limit',50)]:
        cells=tr.find_all('td',recursive=False)
        if len(cells)<7:continue
        company=clean(cells[0].contents[0].strip()) if cells[0].contents and isinstance(cells[0].contents[0],str) else cells[0].get_text(' ',strip=True)
        title=cells[1].get_text(' ',strip=True);location=cells[2].get_text(' ',strip=True)
        kind=cells[4].get_text(' ',strip=True)
        if not title or not company:continue
        category='实习' if '实习' in kind else '企业校招'
        item=normalize(config,old,now,title=title,url=config['url'],company=company,location=location,body='招聘对象：'+cells[3].get_text(' ',strip=True)+'\n公开列表未提供完整职位描述，详情及投递入口请到来源查看。',category=category)
        item['sourceRecordId']=hashlib.sha256((company+'|'+title+'|'+location+'|'+category).encode()).hexdigest()[:24]
        item['id']=hashlib.sha256((config['id']+item['sourceRecordId']).encode()).hexdigest()[:20]
        item['previewKind']='公开列表线索 · 完整详情和投递可能需要登录来源'
        item['sourcePublishedText']=cells[5].get_text(' ',strip=True)
        records.append(item)
    return records

def jsonld_postings(soup):
    output=[]
    def visit(value):
        if isinstance(value,list):
            for item in value:visit(item)
        elif isinstance(value,dict):
            kind=value.get('@type',[])
            if kind=='JobPosting' or isinstance(kind,list) and 'JobPosting' in kind:output.append(value)
            for key in ('@graph','itemListElement','item'):
                if key in value:visit(value[key])
    for script in soup.select('script[type="application/ld+json"]'):
        try:visit(json.loads(script.get_text()))
        except ValueError:pass
    return output

def collect_public_html(config,client,old,now,errors):
    found={};records=[]
    for entry in config.get('list_urls',[config['url']]):
        try:
            soup=client.get(entry)
            entry_count=0
            for a in soup.select('a[href]'):
                url=urljoin(entry,a['href']);title=clean(a.get('title') or a.get_text(' ',strip=True))
                if re.search(config['link_pattern'],url) and 2<=len(title)<=130:
                    found[url]=title
                    entry_count+=1
                    if entry_count>=config.get('per_list_limit',1000):break
        except Exception as exc:errors.append(str(exc)[:140])
    for url,title in list(found.items())[:config.get('limit',50)]:
        try:
            prior=old.get(url)
            if prior and prior.get('detailFetchedAt','')[:10]==now[:10] and prior.get('company'):
                records.extend(prior['_siblings']);continue
            soup=client.get(url);ld=jsonld_postings(soup)
            hero=soup.select_one('[data-job-status]')
            if hero and hero.get('data-job-status') not in ('active','open'):continue
            apply_node=next((soup.select_one(sel) for sel in config.get('apply_selectors',[]) if soup.select_one(sel)),None)
            apply_url=urljoin(url,apply_node['href']) if apply_node and apply_node.get('href') else url
            if ld:
                for row in ld:
                    company=row.get('hiringOrganization') or {}
                    company=company.get('name','') if isinstance(company,dict) else str(company)
                    identifier=row.get('identifier') or {}
                    if company in ('MEG','ACG','WXG','IEG','CDG','CSIG','TEG') and isinstance(identifier,dict):
                        employer=re.sub(r'校园招聘|社会招聘|招聘','',identifier.get('name',''))
                        if employer:company=employer+' · '+company
                    loc=row.get('jobLocation') or [];loc=loc if isinstance(loc,list) else [loc]
                    places=[]
                    for l in loc:
                        address=l.get('address') or {}
                        if isinstance(address,dict):places.append(address.get('addressLocality') or address.get('addressRegion') or '')
                    raw=row.get('description') or row.get('responsibilities') or ''
                    if row.get('qualifications') and row['qualifications'] not in raw:raw+='\n任职要求：'+row['qualifications']
                    body=read_text(BeautifulSoup(raw,'html.parser'))
                    due=deadline('报名截止日期：'+str(row['validThrough'])) if row.get('validThrough') else deadline(body)
                    category='实习' if row.get('employmentType')=='INTERN' or hero and hero.get('data-job-type')=='internship' else '企业校招' if hero and hero.get('data-job-type')=='campus' else None
                    item=normalize(config,old,now,title=row.get('title') or title,url=url,company=company,body=body,location=' '.join(places),published=row.get('datePosted'),due=due,category=category,original_url=apply_url)
                    item['previewKind']='公开聚合页摘录 · 原始官网投递可追溯'
                    records.append(item)
                continue
            for junk in soup.select('script,style,nav,header,footer,aside'):junk.decompose()
            node=next((soup.select_one(sel) for sel in config.get('content_selectors',[]) if soup.select_one(sel)),soup.body or soup)
            body=read_text(node)
            if len(re.findall(r'[\u4e00-\u9fff]',body))<30:raise ValueError('没有可验证的岗位正文')
            heading=soup.select_one('h1');role=heading.get_text(' ',strip=True) if heading else title
            company_node=next((soup.select_one(sel) for sel in config.get('company_selectors',[]) if soup.select_one(sel)),None)
            company=company_node.get_text(' ',strip=True) if company_node else ''
            location_node=next((soup.select_one(sel) for sel in config.get('location_selectors',[]) if soup.select_one(sel)),None)
            location=location_node.get_text(' ',strip=True) if location_node else ''
            salary_node=next((soup.select_one(sel) for sel in config.get('salary_selectors',[]) if soup.select_one(sel)),None)
            salary=salary_node.get_text(' ',strip=True) if salary_node else ''
            records.append(normalize(config,old,now,title=role,url=url,company=company,body=body,location=location,salary=salary))
        except Exception as exc:
            errors.append(f'{title[:20]}：{str(exc)[:100]}')
            if '验证' in str(exc) or 'robots.txt' in str(exc):break
    return records

def collect_enterprise(config,old,now):
    client=SourceClient();errors=[]
    status={'id':config['id'],'name':config['name'],'category':config.get('category','企业社招'),'url':config['url'],'checkedAt':now,'status':'error','count':0}
    try:
        adapter={'zhaopin':collect_zhaopin,'tencent':collect_tencent,'job5156':collect_job5156,'public_table':collect_public_table,'public_html':collect_public_html}[config['adapter']]
        records=adapter(config,client,old,now,errors)
        status.update(status=('partial' if errors else 'ok') if records else 'error',count=len(records),detailsOk=len(records),failedDetails=len(errors),message=f'已读取 {len(records)} 条企业岗位' if records else '未取得公开岗位数据，继续保留其他渠道信息',errors=errors[:5])
        return records,status
    except Exception as exc:
        status['message']=str(exc)[:200];return [],status

def original_key(url):
    p=urlsplit(url);path=p.path.rstrip('/');query=parse_qs(p.query)
    if 'zhaopin.com' in p.netloc:
        match=re.search(r'(CC[A-Za-z0-9]+)\.htm',path)
        if match:return 'zhaopin:'+match[1]
    if 'careers.tencent.com' in p.netloc and query.get('postId'):return 'tencent:'+query['postId'][0]
    if 'zhipin.com' in p.netloc and '/job_detail/' in path:return 'boss:'+path.split('/job_detail/')[-1].split('.')[0]
    # Keep semantic job IDs and discard tracking parameters only.
    useful={k:v for k,v in query.items() if k.lower() in ('id','jobid','postid','positionid','job_id','position_id')}
    return re.sub(r'^www\.','',p.netloc.lower())+path+('?' +urlencode(useful,doseq=True) if useful else '')

def normalized(value):
    return re.sub(r'[\s\W_]+','',unicodedata.normalize('NFKC',value).lower())

def deduplicate(records):
    groups=[];seen_url={};seen_identity={};duplicates=0
    # Prefer actual employer feeds, then fuller descriptions. Preserve all provenance.
    ordered=sorted(records,key=lambda j:(j.get('sourceId')=='tencent',bool(j.get('company')),len(j.get('preview',''))),reverse=True)
    for record in ordered:
        key=original_key(record.get('originalUrl') or record['url'])
        if record.get('sourceRecordId'):key+='#record='+record['sourceRecordId']
        company=normalized(record.get('company',''))
        if record.get('kind')=='position' and not company:
            key+='#role='+record['id']
        known_cities=[c for c in record.get('cities',[]) if '待确认' not in c]
        identity=(company,normalized(record['title']),tuple(sorted(known_cities)),record.get('employmentType') or record.get('category')) if company and known_cities and record.get('kind')=='position' else None
        index=seen_url.get(key)
        if index is None and identity:
            candidate=seen_identity.get(identity)
            # Distinct IDs on one platform may be different teams or vacancies.
            if candidate is not None and groups[candidate]['sourceId']!=record['sourceId']:index=candidate
        source={'name':record['source'],'url':record['url'],'deadline':record['deadline']}
        if index is None:
            item={**record,'sources':list(record.get('sources') or [source])}
            groups.append(item);index=len(groups)-1
            seen_url[key]=index
            if identity:seen_identity[identity]=index
        else:
            duplicates+=1;item=groups[index]
            for source in record.get('sources') or [source]:
                if not any(s['url']==source['url'] and s['name']==source['name'] for s in item['sources']):item['sources'].append(source)
            # Do not merge different cutoff dates by inventing a common deadline.
            if item['deadline'].get('date') and record['deadline'].get('date') and item['deadline']['date']!=record['deadline']['date']:
                item['deadlineConflict']=True
                item['deadline']={'kind':'unknown','date':None,'time':None,'label':'来源截止时间不一致 · 请核实','evidence':None}
    return sorted(groups,key=lambda j:(j.get('updatedAt') or j.get('publishedAt') or '',j['firstSeenAt']),reverse=True),duplicates
