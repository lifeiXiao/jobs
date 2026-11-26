import sys
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from enterprise import initial_state,original_key,deduplicate,normalize,collect_zhaopin,collect_public_html

NOW='2026-11-26T08:00:00+08:00'
CONF={'id':'test','name':'测试来源','url':'https://example.com'}
def job(url,**fields):
    return normalize(CONF,{},NOW,title=fields.pop('title','软件工程师'),url=url,company=fields.pop('company','甲公司'),location=fields.pop('location','南京'),body='岗位职责：软件开发\n专业要求：计算机科学与技术',**fields)

class EnterpriseTests(unittest.TestCase):
    def test_aggregator_long_card_reads_title_and_keeps_campus_and_apply_link(self):
        listing='<a href="/job/1.html"><h2 class="job-title">运输员</h2><p>'+('工作职责'*100)+'</p></a>'
        posting={'@type':'JobPosting','title':'运输员','description':'专业要求：物流管理，工作地点惠州','hiringOrganization':{'name':'比亚迪'},'jobLocation':{'address':{'addressLocality':'广东省惠州市'}},'employmentType':'校招','datePosted':'2026-11-25'}
        import json
        detail='<script type="application/ld+json">'+json.dumps(posting)+'</script><a class="apply-btn" href="https://job.byd.com/portal/pc/#/position/detail?id=1">投递</a>'
        class Client:
            def get(self,url):return BeautifulSoup(detail if url.endswith('.html') else listing,'html.parser')
        config={**CONF,'title_selector':'.job-title','link_pattern':r'/job/\d+\.html$','apply_selectors':['.apply-btn']}
        errors=[]
        jobs=collect_public_html(config,Client(),{},NOW,errors)
        self.assertEqual(errors,[])
        self.assertEqual(len(jobs),1)
        self.assertEqual((jobs[0]['company'],jobs[0]['category'],jobs[0]['cities']),('比亚迪','企业校招',['惠州']))
        self.assertIn('id=1',jobs[0]['originalUrl'])
    def test_static_state_is_json_not_executed(self):
        html='<script>__INITIAL_STATE__={"positionList":[]};evil()</script>'
        self.assertEqual(initial_state(BeautifulSoup(html,'html.parser')),{'positionList':[]})
    def test_platform_url_aliases(self):
        self.assertEqual(original_key('https://jobs.zhaopin.com/CC123J456.htm?utm_source=x'),original_key('https://www.zhaopin.com/jobdetail/CC123J456.htm'))
    def test_hash_route_keeps_different_employer_job_ids(self):
        one='https://job.byd.com/portal/pc/#/position/detail?id=100'
        two='https://job.byd.com/portal/pc/#/position/detail?id=200'
        self.assertNotEqual(original_key(one),original_key(two))
        self.assertEqual(original_key(one),original_key(one+'&utm_source=other'))
    def test_same_company_title_city_merges_sources(self):
        a=job('https://one.example/jobs/1');b=job('https://two.example/jobs/2');b['sourceId']='second'
        items,n=deduplicate([a,b])
        self.assertEqual((len(items),n,len(items[0]['sources'])),(1,1,2))
    def test_different_city_or_seniority_is_preserved(self):
        items,n=deduplicate([job('https://one/1'),job('https://two/2',location='苏州'),job('https://three/3',title='高级软件工程师')])
        self.assertEqual((len(items),n),(3,0))
    def test_unknown_companies_are_not_merged(self):
        items,n=deduplicate([job('https://one/1',company=''),job('https://two/2',company='')])
        self.assertEqual((len(items),n),(2,0))
    def test_conflicting_deadlines_are_not_guessed(self):
        a=job('https://one/1',due={'kind':'date','date':'2026-11-27','label':'11-27'})
        b=job('https://two/2',due={'kind':'date','date':'2026-11-30','label':'11-30'})
        b['sourceId']='second'
        items,_=deduplicate([a,b]);self.assertTrue(items[0]['deadlineConflict']);self.assertEqual(items[0]['deadline']['kind'],'unknown')
    def test_company_search_data_has_no_fabricated_deadline(self):
        item=job('https://one/1')
        self.assertEqual(item['deadline']['kind'],'unknown')
        self.assertIsNone(item['publishedAt'])
        self.assertEqual(item['company'],'甲公司')
    def test_positions_sharing_one_announcement_are_distinct(self):
        a=job('https://school/announcement/1',company='',title='计算机教师')
        b=job('https://school/announcement/1',company='',title='数学教师')
        items,n=deduplicate([a,b]);self.assertEqual((len(items),n),(2,0))
    def test_distinct_job_ids_on_one_platform_are_preserved(self):
        items,n=deduplicate([job('https://board/1'),job('https://board/2')])
        self.assertEqual((len(items),n),(2,0))
    def test_same_title_in_one_announcement_keeps_separate_row_ids(self):
        a=job('https://school/announcement/1',company='',title='专任教师')
        b=job('https://school/announcement/1',company='',title='专任教师')
        a['id']='row1';b['id']='row2';b['majors']=['数学与统计']
        items,n=deduplicate([a,b]);self.assertEqual((len(items),n),(2,0))

if __name__=='__main__':unittest.main()
