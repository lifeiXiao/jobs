import test from'node:test';
import assert from'node:assert/strict';
import{filterJobs,isExpired,toggleSelection,chinaDay}from'../site/logic.mjs';
const now=new Date('2026-11-26T09:00:00+08:00');
const job=(id,majors,cities,date,time=null)=>({id,title:id,announcementTitle:id,preview:'',source:'test',category:'校园招聘',majors,cities,publishedAt:'2026-11-26',firstSeenAt:'2026-11-26T00:00:00+08:00',deadline:{kind:date?'date':'unknown',date,time}});
const jobs=[job('a',['计算机类'],['南京'],'2026-11-30'),job('b',['经济与金融'],['苏州'],'2026-11-27'),job('c',['计算机类'],['南京'],'2026-11-25'),job('d',['法学类'],['北京'],null)];
const base=()=>({majors:new Set(),cities:new Set(),keyword:'',category:'',sort:'newest',hideExpired:true});
test('OR inside groups, AND between groups',()=>{let s=base();s.majors=new Set(['计算机类','经济与金融']);s.cities=new Set(['南京','苏州']);assert.deepEqual(filterJobs(jobs,s,now).map(j=>j.id),['a','b']);s.cities=new Set(['苏州']);assert.deepEqual(filterJobs(jobs,s,now).map(j=>j.id),['b'])});
test('unknown deadline remains visible by default',()=>assert.equal(filterJobs(jobs,base(),now).length,3));
test('date-only stays visible through that day',()=>assert.equal(isExpired(job('a',[],[],'2026-11-26'),now),false));
test('explicit deadline respects China timezone',()=>assert.equal(isExpired(job('a',[],[],'2026-11-26','08:30'),now),true));
test('single and multiple selection both work',()=>{const s=new Set(['a']);toggleSelection(s,'b','single');assert.deepEqual([...s],['b']);toggleSelection(s,'a','multi');assert.equal(s.size,2);toggleSelection(s,'a','multi');assert.deepEqual([...s],['b'])});
test('deadline sort puts unknowns last',()=>{let s=base();s.sort='deadline';assert.deepEqual(filterJobs(jobs,s,now).map(j=>j.id),['b','a','d'])});
test('date is Shanghai even across UTC day boundary',()=>assert.equal(chinaDay(new Date('2026-11-25T17:00:00Z')),'2026-11-26'));
test('keyword handles markup as plain text',()=>{let s=base();s.keyword='<script>';assert.equal(filterJobs(jobs,s,now).length,0)});

test('lazy full-text search matches a requirement absent from the listing',()=>{let s=base();s.keyword='特殊数据库';const j={...jobs[0],searchText:'任职要求：熟悉特殊数据库'};assert.equal(filterJobs([j],s,now).length,1)});
test('same-day listings show different companies before repeating one',()=>{const many=[...jobs.slice(0,2),job('e',['计算机类'],['南京'],'2026-11-30')];many[0].company='甲';many[1].company='甲';many[2].company='乙';const result=filterJobs(many,base(),now);assert.deepEqual(result.map(j=>j.company),['甲','乙','甲'])});
