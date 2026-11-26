"""Build a small listing index; descriptions and full-text search load on demand."""
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def build(root):
    root = Path(root)
    out = root / '_site'
    out.mkdir(exist_ok=True)
    for source in (root / 'site').iterdir():
        if source.is_file():
            shutil.copy2(source, out / source.name)
    data = json.loads((root / 'data/jobs.json').read_text(encoding='utf-8'))
    taxonomy = json.loads((root / 'config/taxonomy.json').read_text(encoding='utf-8'))
    target = out / 'data'
    target.mkdir(exist_ok=True)

    def asset(prefix, value):
        body = compact(value)
        name = prefix + '-' + hashlib.sha256(body).hexdigest()[:16] + '.json'
        (target / name).write_bytes(body)
        return './data/' + name

    buckets = defaultdict(dict)
    for job in data['jobs']:
        assert job['url'].startswith(('https://', 'http://'))
        assert job['id'] and job['title'] and job['cities'] and job['majors']
        buckets[job['id'][:2]][job['id']] = job
    detail_files = {key: asset('detail-' + key, jobs) for key, jobs in buckets.items()}
    fields = ['id', 'title', 'company', 'industry', 'category', 'kind', 'majors', 'cities',
              'degree', 'salary', 'source', 'publishedAt', 'updatedAt', 'firstSeenAt',
              'deadline', 'sourceCount', 'detailFile']
    rows = []
    for job in data['jobs']:
        item = {key: job.get(key) for key in fields}
        item['deadline'] = {key: value for key, value in job.get('deadline', {}).items() if key != 'evidence'}
        item['sourceCount'] = len(job.get('sources', []))
        item['detailFile'] = detail_files[job['id'][:2]]
        rows.append([item[key] for key in fields])
    search = {job['id']: ' '.join(str(job.get(key) or '') for key in ['announcementTitle', 'preview']).lower() for job in data['jobs']}
    index = {key: value for key, value in data.items() if key != 'jobs'}
    index.update(schemaVersion=3, fields=fields, rows=rows, taxonomy=taxonomy, searchFile=asset('search', search))
    index_url = asset('index', index)
    html = (out / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<!-- DATA_INDEX -->', '<meta name="jobs-index" content="' + index_url + '"><link rel="preload" as="fetch" href="' + index_url + '" crossorigin>')
    (out / 'index.html').write_text(html, encoding='utf-8')
    (target / 'jobs.json').write_bytes(compact(data))
    (target / 'taxonomy.json').write_bytes(compact(taxonomy))
    (out / '.nojekyll').touch()
    print(f'Built {len(rows)} records; initial index {len(compact(index)):,} bytes; details in {len(buckets)} lazy buckets')
    return index


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
