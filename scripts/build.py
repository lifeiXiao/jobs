import json
import shutil
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=root/'_site'
out.mkdir(exist_ok=True)
for source in (root/'site').iterdir():
    if source.is_file(): shutil.copy2(source,out/source.name)
(out/'data').mkdir(exist_ok=True)
shutil.copy2(root/'config/taxonomy.json',out/'data/taxonomy.json')
data=root/'data/jobs.json'
if not data.exists():
    data.parent.mkdir(exist_ok=True)
    data.write_text(json.dumps({'schemaVersion':1,'lastAttemptAt':None,'lastSuccessfulAt':None,'jobs':[],'sources':[]}),encoding='utf-8')
payload=json.loads(data.read_text(encoding='utf-8'))
assert isinstance(payload['jobs'],list) and isinstance(payload['sources'],list)
for job in payload['jobs']:
    assert job['url'].startswith(('https://','http://'))
    assert job['id'] and job['title'] and job['cities'] and job['majors']
shutil.copy2(data,out/'data/jobs.json')
(out/'.nojekyll').touch()
print(f'Built {out} with {len(payload["jobs"])} records')
