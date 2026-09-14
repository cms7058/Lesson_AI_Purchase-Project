/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:18003/api/v1';
const headers={'Content-Type':'application/json','X-User-Role':'procurement_manager'};
async function request(path,method='GET',data){const r=await fetch(base+path,{method,headers,body:data?JSON.stringify(data):undefined});assert(r.ok,await r.clone().text());return r.status===204?null:r.json();}
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const tag=Date.now().toString();
 const order=await request('/orders','POST',{supplier_id:'QA',supplier_name:'隔离测试供应商',factory_code:'QA',lines:[{material_code:'QA-'+tag,material_name:'测试物料',unit:'件',quantity:10,unit_price:100,tax_rate:0.13}]});
 // Forward to a real isolated server. No response data is fabricated.
 await page.route('**/api/v1/**',async r=>{const u=new URL(r.request().url());const response=await r.fetch({url:'http://127.0.0.1:18003'+u.pathname+u.search});await r.fulfill({response});});
 try{
  await page.goto('http://localhost:8080/projects',{waitUntil:'networkidle'});await page.getByRole('button',{name:'新建项目',exact:true}).click();
  let d=page.locator('.el-dialog:visible').first();
  const field=label=>d.locator('.el-form-item').filter({has:page.locator('.el-form-item__label',{hasText:label})}).locator('input').first();
  await field('项目编号').fill('QA-'+tag);await field('项目名称').fill('真实操作验收');await d.getByRole('button',{name:'保存项目',exact:true}).click();
  const row=page.locator('.el-table__row').filter({hasText:'QA-'+tag});await row.getByRole('button',{name:'编辑 / 甘特图'}).click();
  await d.getByRole('tab',{name:'采购成本',exact:true}).click();await d.getByRole('button',{name:'关联采购明细',exact:true}).click();
  let modal=page.getByRole('dialog',{name:'采购明细分摊',exact:true});await modal.getByPlaceholder('订单号或物料编码').fill(order.order_no);await modal.getByRole('button',{name:'搜索订单行',exact:true}).click();
  await modal.locator('.el-radio').first().click();const quantity=modal.locator('.el-input-number input');await quantity.fill('11');await quantity.press('Tab');await modal.getByRole('button',{name:'保存分摊',exact:true}).click();
  await page.getByText('各项目分摊数量合计不能超过订单行数量',{exact:true}).waitFor();
  await quantity.fill('2');await quantity.press('Tab');await modal.getByRole('button',{name:'保存分摊',exact:true}).click();await modal.waitFor({state:'hidden'});
  const project=(await request('/projects?keyword=QA-'+tag)).items[0];let costs=await request('/project-costs/'+project.id);assert.equal(costs.draft,226);assert.equal(costs.rows.length,1);
  await d.getByRole('button',{name:'编辑',exact:true}).click();modal=page.getByRole('dialog',{name:'采购明细分摊',exact:true});await modal.locator('.el-input-number input').fill('3');await modal.locator('.el-input-number input').press('Tab');await modal.getByRole('button',{name:'保存分摊',exact:true}).click();await modal.waitFor({state:'hidden'});
  costs=await request('/project-costs/'+project.id);assert.equal(costs.draft,339);
  await page.reload({waitUntil:'networkidle'});await page.locator('.el-table__row').filter({hasText:'QA-'+tag}).getByRole('button',{name:'编辑 / 甘特图'}).click();d=page.locator('.el-dialog:visible').first();await d.getByRole('tab',{name:'采购成本',exact:true}).click();await d.getByRole('cell',{name:'339',exact:true}).waitFor();
  await d.getByRole('button',{name:'移除',exact:true}).click();await Promise.all([page.waitForResponse(r=>r.request().method()==='DELETE'),page.locator('.el-message-box').getByRole('button',{name:'确定',exact:true}).click()]);
  costs=await request('/project-costs/'+project.id);assert.equal(costs.rows.length,0);assert.deepEqual(errors,[]);
  console.log('PASS real backend: project creation, allocation validation/create/edit/reload/delete and database readback; isolated DB only');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
