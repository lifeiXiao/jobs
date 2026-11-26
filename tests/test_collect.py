import sys
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect import deadline,classify,cities,positions,merge,publication

class ExtractionTests(unittest.TestCase):
    def test_full_range_end_not_start(self):
        d=deadline('报名时间：2026年11月1日9:00至2026年11月30日17:30。')
        self.assertEqual((d['date'],d['time']),('2026-11-30','17:30'))
    def test_short_range(self):
        d=deadline('报名时间：2026年11月1日至11月30日17时。')
        self.assertEqual((d['date'],d['time']),('2026-11-30','17:00'))
    def test_beginning_is_not_deadline(self):
        self.assertEqual(deadline('报名时间：2026年11月1日起开始接受申请。')['kind'],'unknown')
    def test_exam_date_not_deadline(self):
        self.assertEqual(deadline('笔试时间2026年12月1日。发布日期2026-11-26')['kind'],'unknown')
    def test_unspecified_time_not_invented(self):
        d=deadline('报名截止时间：2026-11-30。')
        self.assertIsNone(d['time'])
    def test_open_and_unknown(self):
        self.assertEqual(deadline('本次招聘招满即止')['kind'],'open')
        self.assertEqual(deadline('详见岗位表')['kind'],'unknown')
    def test_invalid_date(self):
        self.assertEqual(deadline('报名截止：2026年2月30日。')['kind'],'unknown')
    def test_publication_meta(self):
        self.assertEqual(publication(BeautifulSoup('<meta name="publishdate" content="2026-11-26">','html.parser'),''),'2026-11-26')
    def test_classification(self):
        self.assertEqual(classify('所学专业：计算机科学与技术、金融学'),['计算机类','经济与金融'])
        self.assertEqual(classify('专业：不限专业'),['专业不限'])
        self.assertEqual(classify('欢迎投递'),['专业待确认'])
    def test_cities_do_not_use_footer(self):
        self.assertEqual(cities('工作地点：苏州\n联系我们：北京','某公司招聘'),['苏州'])
        self.assertEqual(cities('联系地址：北京','某公司招聘'),['城市待确认'])
    def test_table_positions(self):
        html='<table><tr><th>岗位名称</th><th>专业要求</th><th>学历</th></tr><tr><td>开发工程师</td><td>软件工程</td><td>本科</td></tr></table>'
        rows=positions(BeautifulSoup(html,'html.parser'))
        self.assertEqual(rows[0][0],'开发工程师')
        self.assertIn('专业要求：软件工程',rows[0][1])
    def test_preserve_old_on_failure(self):
        old=[{'id':'a','firstSeenAt':'2026-11-01T08:00:00+08:00','title':'old'}]
        self.assertEqual(merge(old,[],'2026-11-26T08:00:00+08:00'),old)
    def test_dedup_and_retention(self):
        old=[{'id':'a','firstSeenAt':'2026-01-01T08:00:00+08:00'}]
        fresh=[{'id':'b','firstSeenAt':'2026-11-26T08:00:00+08:00','title':'new'}]
        self.assertEqual(merge(old,fresh+fresh,'2026-11-26T08:00:00+08:00'),fresh)

if __name__=='__main__': unittest.main()
