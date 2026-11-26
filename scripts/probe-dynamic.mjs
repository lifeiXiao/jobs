import{chromium}from'playwright';
import fs from'node:fs/promises';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1365,height:1000}});
await fs.mkdir('dynamic-probe',{recursive:true});
for(const[url,name]of[['https://www.zhipin.com/web/geek/jobs?city=100010000','boss']]){
  try{
    await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
    await page.waitForTimeout(8000);
    const body=await page.locator('body').innerText();
    const gate=/安全验证|验证码|访问异常|请完成验证|请稍候|verify|security/i.test((await page.title())+' '+body.slice(0,1500));
    const jobs=gate?[]:await page.locator('a[href*="/job_detail/"]').evaluateAll(as=>as.map(a=>({url:a.href,title:a.textContent.trim()})).filter(x=>x.title));
    const result={source:url,finalUrl:page.url(),title:await page.title(),accessGate:gate,publicJobCount:jobs.length,jobs:jobs.slice(0,40)};
    console.log(JSON.stringify(result));
    await fs.writeFile(`dynamic-probe/${name}.json`,JSON.stringify(result,null,2));
    await page.screenshot({path:`dynamic-probe/${name}.png`});
  }catch(error){console.log(name+': '+error.message)}
}
await browser.close();
