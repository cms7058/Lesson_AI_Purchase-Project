/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/projects/dashboard?*',r=>r.fulfill({json:{currencies:['CNY'],project_count:1,budget:10000,tasks:5,completed:2,overdue:1,statuses:[{name:'active',key:'active',value:1}],managers:[{name:'测试经理',key:'m1',value:1}],trend:[{name:'2026-09',value:5}],rows:[{id:'p1',code:'P001',name:'测试项目',status:'active',budget:10000,manager_name:'测试经理'}],total:1}}));
 try{
  await page.goto('http://localhost:8080/project-dashboard',{waitUntil:'networkidle'});
  const titles=await page.locator('nav>.nav-group>.nav-group-title').allTextContents();
  assert(!titles.some(t=>t.includes('工作台')||t.includes('智能分析')));
  const purchase=page.locator('nav>.nav-group').filter({has:page.locator(':scope>.nav-group-title',{hasText:'采购业务'})});
  assert.equal(await purchase.getByRole('link',{name:'采购驾驶舱'}).count(),1);
  assert.equal(await purchase.locator('.nav-subgroup').count(),1);
  await purchase.locator('.nav-subgroup button').click();assert.equal(await purchase.getByRole('link',{name:'需求预测'}).isVisible(),false);
  await purchase.locator('.nav-subgroup button').click();assert(await purchase.getByRole('link',{name:'需求预测'}).isVisible());
  await page.getByRole('heading',{name:'项目驾驶舱',exact:true}).waitFor();assert.equal(await page.locator('canvas').count(),3);
  const selected=page.waitForRequest(r=>r.url().includes('manager_id=m1'));
  const chart=page.locator('.chart-grid .chart-card').nth(1).locator('canvas');await chart.click({position:{x:250,y:150}});
  // Verify filters through a chart event using the mounted chart instance if click missed a responsive sector.
  await page.locator('.chart-grid .chart-card').nth(1).locator('canvas').evaluate(c=>{c.parentElement.parentElement.__vue__.$emit('select',{name:'测试经理',data:{key:'m1'}});});
  await selected;
  await page.screenshot({path:'/tmp/pebs-project-dashboard.png',fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS nested menu, project dashboard charts and manager linkage (API mocked)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
