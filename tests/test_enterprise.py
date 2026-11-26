import sys
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from enterprise import initial_state,original_key,deduplicate,normalize,collect_zhaopin

NOW='2026-11-26T08:00:00+08:00'
CONF={'id':'test','name':'测试来源','url':'https://example.com'}
def job(url,**fields):
    return normalize(CONF,{},NOW,title=fields.pop('title','软件工程师'),url=url,company=fields.pop('company','甲公司'),location=fields.pop('location','南京'),body='岗位职责：软件开发\n专业要求：计算机科学与技术',**fields)

class EnterpriseTests(unittest.TestCase):
    def test_static_state_is_json_not_executed(self):
        html='<script>__INITIAL_STATE__={"positionList":[]};evil()</script>'
        self.assertEqual(initial_state(BeautifulSoup(html,'html.parser')),{'positionList':[]})
    def test_platform_url_aliases(self):
        self.assertEqual(original_key('https://jobs.zhaopin.com/CC123J456.htm?utm_source=x'),original_key('https://www.zhaopin.com/jobdetail/CC123J456.htm'))
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

if __name__=='__main__':unittest.main()
