import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build import build


class BuildTests(unittest.TestCase):
    def test_lazy_snapshot_keeps_every_detail_and_search_term(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ['site', 'data', 'config']:
                (root / folder).mkdir()
            (root / 'site/index.html').write_text('<!-- DATA_INDEX -->', encoding='utf-8')
            (root / 'config/taxonomy.json').write_text('{"majors":{},"cities":[]}', encoding='utf-8')
            jobs = [{'id': key, 'title': '工程师', 'url': 'https://example.com/' + key,
                     'majors': ['计算机类'], 'cities': ['南京'], 'preview': '要求掌握特殊数据库',
                     'attachments': [{'name': '岗位表', 'url': 'https://example.com/jobs.pdf'}],
                     'deadline': {'kind': 'date', 'date': '2026-12-01', 'evidence': '投递截至12月1日'}}
                    for key in ['aa0001', 'bb0002', 'aa0003']]
            (root / 'data/jobs.json').write_text(json.dumps({'jobs': jobs, 'sources': []}), encoding='utf-8')
            index = build(root)
            self.assertNotIn('特殊数据库', json.dumps(index, ensure_ascii=False))
            search = json.loads((root / '_site' / index['searchFile'][2:]).read_text(encoding='utf-8'))
            self.assertIn('特殊数据库', search['aa0001'])
            for row, original in zip(index['rows'], jobs):
                job = dict(zip(index['fields'], row))
                detail = json.loads((root / '_site' / job['detailFile'][2:]).read_text(encoding='utf-8'))
                self.assertEqual(detail[job['id']], original)
                self.assertNotIn('evidence', job['deadline'])
            html = (root / '_site/index.html').read_text(encoding='utf-8')
            self.assertIn('rel="preload"', html)
            self.assertEqual(len(list((root / '_site/data').glob('detail-*.json'))), 2)
            original_index = html
            jobs[0]['preview'] += '新增要求'
            (root / 'data/jobs.json').write_text(json.dumps({'jobs': jobs, 'sources': []}), encoding='utf-8')
            build(root)
            self.assertNotEqual((root / '_site/index.html').read_text(encoding='utf-8'), original_index)
