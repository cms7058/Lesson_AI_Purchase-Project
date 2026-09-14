/* eslint-env node */
const {chromium,request}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const api=await request.newContext({baseURL:'http://127.0.0.1:18001',extraHTTPHeaders:{'X-User-Role':'admin'}});
 const tag='FILTER-'+Date.now();
 for(let i=0;i<12;i++){
  const r=await api.post('/api/v1/orders',{data:{supplier_id:tag,supplier_name:tag,factory_code:'F1',lines:[{material_code:tag,material_name:'组合查询测试',quantity:5,unit:'件',unit_price:10}]}});
  assert(r.ok(),await r.text());
 }
 const seed=await api.post('/api/v1/supply-feedback/demo');assert(seed.ok());
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/api/v1/**',async route=>{const u=new URL(route.request().url());const r=await route.fetch({url:`http://127.0.0.1:18001${u.pathname}${u.search}`});if(r.status()>=400)errors.push(u.pathname+' '+r.status());await route.fulfill({response:r});});
 async function option(select,label){await select.click();await page.locator('.el-select-dropdown:visible').getByText(label,{exact:true}).click();}
 async function add(field,value){const panel=page.locator('.combined-filter').first();await panel.getByRole('button',{name:'添加条件',exact:true}).click();const row=panel.locator('.filter-condition').last();await option(row.locator('.el-select').first(),field);await row.locator('.el-input').last().locator('input').fill(value);}
 async function search(resource){const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/'+resource&&r.request().method()==='GET'&&r.url().includes('filters'));await page.locator('.combined-filter').first().getByRole('button',{name:'组合查询',exact:true}).click();return (await response).json();}
 try{
  await page.goto('http://localhost:8080/orders',{waitUntil:'networkidle'});await add('供应商',tag);await add('物料编码',tag);
  const result=await search('orders');assert.equal(result.total,12);assert.equal(result.items.length,10);
  const next=page.waitForResponse(r=>r.url().includes('/orders?')&&r.url().includes('page=2'));await page.locator('.pagination-row .btn-next').click();assert.equal((await(await next).json()).items.length,2);
  await page.waitForTimeout(300);await page.screenshot({path:'/tmp/pebs-combined-orders.png',fullPage:true});
  await page.getByRole('button',{name:'质量追溯',exact:true}).first().click();await page.locator('.el-dialog:visible').getByText('收货历史',{exact:true}).waitFor();await page.locator('.el-dialog:visible .el-dialog__headerbtn').click();
  const pages={'/requisitions':['采购申请'],'/rfqs':['询价项目'],'/suppliers':['供应商','物料','工厂'],'/fulfillment':['收货','质检','退货'],'/settlements':['对账','发票','付款'],'/contracts':['合同'],'/materials':['物料分类','物料','供应商物料分类'],'/personnel':['人员','采购授权'],'/forecast':['需求预测'],'/sourcing':['寻源项目'],'/routing':['路径规划'],'/reports':['报告','审计日志'],'/templates':['模板'],'/data-sources':['数据接入'],'/workflows':['工作流','工作流执行','通知']};
  const schemas=await(await api.get('/api/v1/list-filter-schema')).json();
  for(const [path,labels] of Object.entries(pages)){
   await page.goto('http://localhost:8080'+path,{waitUntil:'networkidle'});
   for(const label of labels){
    const panel=page.locator('.combined-filter').first();await option(panel.locator('.filter-heading .el-select'),label);await page.waitForLoadState('networkidle');
    const schema=schemas.find(s=>s.label===label);await add(schema.fields[0].label,'NOT-FOUND-'+tag);
    const r=await search(schema.resource);assert.equal(r.total,0,label);await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('.page > div .el-table__body-wrapper .el-table__row:visible').count(),0,label+' stale rows');
    console.log('PASS query UI '+label);
   }
  }
  await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});await page.locator('.el-table__row').filter({hasText:'DEMO-FB-RFQ'}).getByRole('button',{name:'定标',exact:true}).click();let dialog=page.locator('.el-dialog:visible').last();await dialog.getByText('2. TOC分析定标',{exact:true}).click();await dialog.getByRole('button',{name:'生成当前询价模拟数据',exact:true}).click();await page.locator('.el-message-box:visible').getByRole('button',{name:'确定',exact:true}).click();await page.getByText('演示批次已生成；不修改报价、不参与正式定标',{exact:true}).waitFor();
  assert(await dialog.getByRole('button',{name:'确认TOC定标',exact:true}).isDisabled());assert(await dialog.locator('canvas').count());await page.waitForTimeout(500);await page.screenshot({path:'/tmp/pebs-context-tco.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS all combined filters, pagination, order trace and contextual TOC demo');
 }catch(e){await page.screenshot({path:'/tmp/pebs-combined-failure.png',fullPage:true});throw e;}finally{await browser.close();await api.dispose();}
})().catch(e=>{console.error(e);process.exit(1);});
