/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://localhost:8080/procurement-dashboard',{waitUntil:'networkidle'});
  await page.locator('.cockpit .el-table__row').first().waitFor();
  assert.equal(await page.getByText('核心模块',{exact:true}).count(),0);
  const total=await page.locator('.cockpit').evaluate(el=>el.__vue__.data.total);
  await page.locator('.cockpit').evaluate(el=>{const v=el.__vue__;v.selectStatus({data:v.data.order_status[0],name:v.data.order_status[0].name});});
  await page.waitForResponse(r=>r.url().includes('/analytics/cockpit')&&r.status()===200);
  await page.waitForLoadState('networkidle');
  assert(await page.locator('.cockpit').evaluate(el=>el.__vue__.data.total)<=total);
  await page.getByRole('button',{name:'重置筛选',exact:true}).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.locator('.cockpit').evaluate(el=>el.__vue__.selectBuyer({dataIndex:0}));
  await page.waitForFunction(()=>{const v=document.querySelector('.cockpit').__vue__;return !v.loading&&v.buyer;});
  assert(await page.locator('.cockpit').evaluate(el=>el.__vue__.data.buyer_stats.length)===1);
  await page.getByRole('button',{name:'重置筛选',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.cockpit').__vue__.loading);
  await page.getByRole('button',{name:'指定采购员',exact:true}).first().click();
  await page.getByText('指定订单责任采购员',{exact:true}).waitFor();
  await page.locator('.el-dialog:visible').last().getByRole('button',{name:'取消',exact:true}).click();
  await page.waitForTimeout(1000);
  await page.screenshot({path:'/tmp/pebs-cockpit-linked.png',fullPage:true});
  await page.locator('.ai-fab').click();
  const dialog=page.locator('.assistant-dialog');
  await dialog.getByRole('button',{name:'查询订单',exact:true}).click();
  await dialog.locator('.ai-result .el-table__row').first().waitFor();
  assert(await dialog.locator('canvas').count()>0);
  if(await dialog.locator('.btn-next:not([disabled])').count()){
   await dialog.locator('.btn-next').click();await dialog.getByText(/第 2 页/).waitFor();
  }
  await page.screenshot({path:'/tmp/pebs-assistant-results.png'});
  await dialog.locator('.el-dialog__headerbtn').click();
  await page.locator('a[href="/orders"]').first().click();
  await page.locator('.ai-fab').click();
  await dialog.locator('.ai-result').first().waitFor(); // Conversation survives navigation.
  for(const label of ['查询询价单','查询供应商','查询物料','查询价格','查询人员','查询权限']){
   const response=page.waitForResponse(r=>r.url().endsWith('/assistant/chat')&&r.request().method()==='POST');
   await dialog.getByRole('button',{name:label,exact:true}).click();assert.equal((await response).status(),200);
   await page.waitForFunction(()=>!document.querySelector('.assistant-dialog .ai-chat').__vue__.sending);
  }
  await dialog.locator('.el-dialog__headerbtn').click();
  await page.goto('http://localhost:8080/supplier',{waitUntil:'networkidle'});
  await page.locator('.ai-fab').click();
  await dialog.getByRole('button',{name:'查询订单',exact:true}).click();
  await dialog.getByText('请先登录供应商账号',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  const bounds=await dialog.boundingBox();assert(bounds.width<=390);
  assert.deepEqual(errors,[]);
  console.log('PASS: cockpit filters, global assistant, preserved conversation, 7 query types, paging, supplier login gate, responsive dialog');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
