/* eslint-env node */
const {chromium, request}=require('playwright');
const assert=require('node:assert/strict');

(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:18001',extraHTTPHeaders:{'X-User-Role':'procurement_manager','X-User-Id':'ui-edit-test'}});
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/v1/**',async route=>{const u=new URL(route.request().url());const response=await route.fetch({url:`http://127.0.0.1:18001${u.pathname}${u.search}`});await route.fulfill({response});});
  try{
    for(const kind of ['orders']){
      const tag=`UI-EDIT-${Date.now()}`;
      const result=await api.post(`/api/v1/${kind}`,{data:{supplier_id:tag,supplier_name:tag,factory_code:'UI-F',lines:[{material_code:tag,material_name:'浏览器编辑测试',quantity:10,unit_price:20,unit:'件'}]}});
      assert(result.ok(),await result.text());const record=await result.json();
      await page.goto(`http://localhost:8080/${kind}`,{waitUntil:'networkidle'});
      await page.locator('.el-table__row').filter({hasText:tag}).getByRole('button',{name:'编辑',exact:true}).click();
      const dialog=page.locator('.el-dialog:visible');
      const field=label=>dialog.locator('.el-form-item').filter({has:page.locator('.el-form-item__label',{hasText:new RegExp(`^${label}$`)})}).locator('input');
      await field(kind==='orders'?'供应商':'供应商名称').fill(`${tag}-修改`);
      if(kind==='orders'){await field('数量 / 单价').nth(0).fill('7');await field('数量 / 单价').nth(1).fill('31');}
      else{await field('数量').fill('7');await field('单价').fill('31');}
      const saved=page.waitForResponse(r=>r.url().includes(`/api/v1/${kind}/${record.id}`)&&r.request().method()==='PATCH');
      await dialog.getByRole('button',{name:kind==='orders'?'保存修改':'保存报价',exact:true}).click();
      assert.equal((await saved).status(),200);
      await dialog.waitFor({state:'hidden'});
      await page.reload({waitUntil:'networkidle'});
      await page.locator('.el-table__row').filter({hasText:`${tag}-修改`}).getByRole('button',{name:'编辑',exact:true}).click();
      assert.equal(Number(await field(kind==='orders'?'数量 / 单价':'数量').first().inputValue()),7);
      assert.equal(Number(await field(kind==='orders'?'数量 / 单价':'单价').nth(kind==='orders'?1:0).inputValue()),31);
      await dialog.locator('.el-dialog__headerbtn').click();
      const deleted=await api.delete(`/api/v1/${kind}/${record.id}`);assert.equal(deleted.status(),204);
      console.log(`PASS ${kind}: edit supplier/quantity/price, save, reload and verify`);
    }
    assert.deepEqual(errors,[]);
  }finally{await browser.close();await api.dispose();}
})().catch(e=>{console.error(e);process.exit(1);});
