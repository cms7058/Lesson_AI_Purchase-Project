/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});
  await page.locator('.el-table__row').filter({hasText:'DEMO-XJ-001'}).getByRole('button',{name:'定标',exact:true}).click();
  const dialog=page.locator('.el-dialog:visible').last();
  await dialog.getByText('2. TOC分析定标',{exact:true}).click();
  await dialog.getByText(/当前展示独立模拟案例 DEMO-FB-RFQ/).waitFor();
  assert.equal(await dialog.locator('.el-table__body-wrapper').first().locator('.el-table__row').count(),3);
  assert(await dialog.locator('canvas').count());
  const normal=dialog.locator('.toc-distribution');
  await normal.getByText('实际分布与正态参考曲线',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.toc-distribution')?.__vue__?.stats?.normal_curve?.length>0);
  assert(await normal.evaluate(el=>el.__vue__.stats.n>=18));
  for(const metric of ['质量合格率(%)','准时交付率(%)','返工率(%)','响应时长(小时)']){
   await normal.locator('.el-select').nth(2).click();
   await page.locator('.el-select-dropdown:visible').getByText(metric,{exact:true}).click();
   await page.waitForFunction(label=>{const v=document.querySelector('.toc-distribution')?.__vue__;return v&&!v.loading&&v.labels[v.metric]===label&&v.stats.n>=18;},metric);
   assert(await normal.evaluate(el=>el.__vue__.stats.n>=18));
   assert(await normal.evaluate(el=>el.__vue__.stats.normal_curve.length>0));
  }
  await normal.getByText('查看正态 Q-Q 图和原始批次数据',{exact:true}).click();
  await normal.locator('.el-table__row').first().waitFor();
  assert.equal(await normal.locator('canvas').count(),3);
  await normal.locator('h3').evaluate(el=>el.scrollIntoView({block:'start'}));
  await page.waitForTimeout(400);await page.screenshot({path:'/tmp/pebs-toc-normal.png',fullPage:true});
  assert(await dialog.getByRole('button',{name:'确认TOC定标',exact:true}).isDisabled());
  await page.waitForTimeout(500);await page.screenshot({path:'/tmp/pebs-toc-visible.png',fullPage:true});
  const restored=page.waitForResponse(r=>r.url().includes('/award-analysis')&&r.url().includes('include_demo=false'));
  await dialog.getByText('1. 最低价中标',{exact:true}).click();
  await restored;
  await page.waitForLoadState('networkidle');
  assert.equal(await dialog.getByText(/当前展示独立模拟案例/).count(),0);
  assert.equal(await dialog.locator('.el-table__body-wrapper').first().locator('.el-table__row').count(),1);
  assert.deepEqual(errors,[]);console.log('PASS: TOC preview automatically visible, 3 suppliers, chart, award blocked, switching back restores actual RFQ');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
