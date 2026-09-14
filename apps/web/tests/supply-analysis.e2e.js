/* eslint-env node */
const {chromium,request}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const api=await request.newContext({baseURL:'http://127.0.0.1:18001',extraHTTPHeaders:{'X-User-Role':'procurement_manager'}});
 const seeded=await api.post('/api/v1/supply-feedback/demo');assert(seeded.ok(),await seeded.text());
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/api/v1/**',async route=>{const u=new URL(route.request().url());const r=await route.fetch({url:`http://127.0.0.1:18001${u.pathname}${u.search}`});await route.fulfill({response:r});});
 try{
  await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});assert.equal(await page.locator('nav a[href="/material-costs"]').count(),0);
  await page.locator('.el-table__row').filter({hasText:'DEMO-FB-RFQ'}).getByRole('button',{name:'定标',exact:true}).click();
  let dialog=page.locator('.el-dialog:visible').last();await dialog.getByText('1. 最低价中标',{exact:true}).waitFor();await dialog.getByText('2. TOC分析定标',{exact:true}).click();
  await page.waitForLoadState('networkidle');await page.waitForTimeout(500);
  assert(await dialog.locator('canvas').count());await dialog.getByText('DEMO-FB-M001',{exact:true}).count();assert(await dialog.getByRole('button',{name:'确认TOC定标',exact:true}).isDisabled());
  await page.waitForTimeout(500);await page.screenshot({path:'/tmp/pebs-tco-award.png',fullPage:true});
  await page.goto('http://localhost:8080/suppliers',{waitUntil:'networkidle'});await page.getByRole('button',{name:'查看物料供货指标',exact:true}).click();dialog=page.locator('.el-dialog:visible').last();
  await page.waitForLoadState('networkidle');await page.waitForTimeout(500);
  const stat=page.locator('.el-dialog:visible').last();await stat.getByText('实际分布与正态参考曲线',{exact:true}).waitFor();assert.equal(await stat.locator('canvas').count(),3);await page.waitForTimeout(500);await page.screenshot({path:'/tmp/pebs-supplier-statistics.png',fullPage:true});
  await page.goto('http://localhost:8080/data-sources',{waitUntil:'networkidle'});await page.locator('.el-table__row').filter({hasText:'【模拟】WMS/MES供货反馈'}).getByRole('button',{name:'供货反馈接入',exact:true}).click();dialog=page.locator('.el-dialog:visible').last();
  const download=page.waitForEvent('download');await dialog.getByRole('button',{name:'下载导入模板（CSV）',exact:true}).click();assert.equal((await download).suggestedFilename(),'supply-feedback-template.csv');
  await dialog.getByRole('button',{name:'设置说明 / 字段字典',exact:true}).click();const guide=page.locator('.el-dialog:visible').last();await guide.getByText('JSON推送示例',{exact:true}).waitFor();await guide.getByRole('button',{name:'关闭',exact:true}).click();
  const content=`external_id,supplier_code,material_code,record_date,received_quantity,inspected_quantity,accepted_quantity,on_time_quantity,response_hours\nUI-${Date.now()},DEMO-FB-S1,DEMO-FB-M001,2026-09-01,100,100,99,98,2\n`;
  await dialog.locator('input[type=file]').setInputFiles({name:'feedback.csv',mimeType:'text/csv',buffer:Buffer.from(content)});await page.getByText('新增 1 条，重复跳过 0 条',{exact:true}).first().waitFor();
  assert.deepEqual(errors,[]);console.log('PASS: two award methods, per-material regression charts, simulated award disabled, supplier normal/median charts, CSV template/help/import');
 }catch(e){await page.waitForTimeout(500);await page.screenshot({path:'/tmp/pebs-analysis-failure.png',fullPage:true});throw e;}finally{await browser.close();await api.dispose();}
})().catch(e=>{console.error(e);process.exit(1);});
