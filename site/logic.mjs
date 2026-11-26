export function chinaDay(now=new Date()){return new Date(now.getTime()+8*3600000).toISOString().slice(0,10)}
export function isExpired(job,now=new Date()){
  const d=job.deadline;
  if(d?.kind!=='date'||!d.date)return false;
  if(d.time)return new Date(`${d.date}T${d.time}:00+08:00`).getTime()<now.getTime();
  return d.date<chinaDay(now);
}
export function daysLeft(job,now=new Date()){
  if(!job.deadline?.date)return null;
  return Math.round((Date.parse(job.deadline.date+'T00:00:00+08:00')-Date.parse(chinaDay(now)+'T00:00:00+08:00'))/86400000);
}
export function filterJobs(jobs,state,now=new Date()){
  const words=state.keyword.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const weekStart=state.weekOnly?chinaDay(new Date(now.getTime()-6*86400000)):null;
  let result=jobs.filter(job=>{
    if(state.hideExpired&&isExpired(job,now))return false;
    if(state.onlyDated&&job.deadline?.kind!=='date')return false;
    if(state.weekOnly&&(!job.publishedAt||job.publishedAt<weekStart))return false;
    if(state.majors.size&&!job.majors.some(x=>state.majors.has(x)))return false;
    if(state.cities.size&&!job.cities.some(x=>state.cities.has(x)))return false;
    if(state.category&&job.category!==state.category)return false;
    if(!words.length)return true;
    const haystack=[job.title,job.announcementTitle,job.company,job.industry,job.preview,job.searchText,job.source,...job.majors,...job.cities].join(' ').toLowerCase();
    return words.every(word=>haystack.includes(word));
  });
  if(state.sort==='deadline')result.sort((a,b)=>(a.deadline?.date||'9999').localeCompare(b.deadline?.date||'9999')||(a.deadline?.time||'23:59').localeCompare(b.deadline?.time||'23:59'));
  else {
    result.sort((a,b)=>(b.updatedAt||b.publishedAt||'').localeCompare(a.updatedAt||a.publishedAt||'')||b.firstSeenAt.localeCompare(a.firstSeenAt));
    const byDay=new Map();
    for(const job of result){const date=job.updatedAt||job.publishedAt||'';if(!byDay.has(date))byDay.set(date,new Map());const companies=byDay.get(date);const key=job.company||job.id;if(!companies.has(key))companies.set(key,[]);companies.get(key).push(job)}
    result=[];
    for(const companies of byDay.values()){let remaining=true;while(remaining){remaining=false;for(const queue of companies.values())if(queue.length){result.push(queue.shift());remaining=true}}}
  }
  return result;
}
export function toggleSelection(selected,value,mode){
  if(selected.has(value)){selected.delete(value);return}
  if(mode==='single')selected.clear();
  selected.add(value);
}
