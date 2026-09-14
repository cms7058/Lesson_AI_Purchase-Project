/* eslint-env node */
const {chromium,request}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:18001/api/v1',extraHTTPHeaders:{'X-User-Role':'admin','X-User-Id':'portal-ui-test'}});
  async function post(path,data){const r=await api.post('/api/v1'+path,{data});assert(r.ok(),await r.text());return r.json();}
  const tag=Date.now();const suppliers=[];
  for(let i=0;i<3;i++){const s=await post('/suppliers',{code:`UI-S-${tag}-${i}`,name:`门户测试供应商${i}-${tag}`,status:'qualified',email:`s${i}@example.invalid`});suppliers.push(s);const r=await api.put('/api/v1/supplier-accounts',{data:{supplier_id:s.id,username:`ui-${tag}-${i}`,password:'Ui-test-password-123!'}});assert(r.ok(),await r.text());}
  const rfq=await post('/rfqs',{title:`在线回标验收-${tag}`,deadline:'2099-12-31',lines:[{material_code:`UI-M-${tag}`,material_name:'精密轴',quantity:10,unit:'件'}],invitations:suppliers.map(s=>({supplier_id:s.code,supplier_name:s.name}))});
  const uploaded=await api.post(`/api/v1/rfqs/${rfq.id}/attachments`,{multipart:{file:{name:'spec.txt',mimeType:'text/plain',buffer:Buffer.from('specification')}}});assert(uploaded.ok(),await uploaded.text());
  const browser=await chromium.launch({headless:true});
  let internalRole='procurement_manager';
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.route('**/api/v1/**',async route=>{const u=new URL(route.request().url());const r=await route.fetch({url:`http://127.0.0.1:18001${u.pathname}${u.search}`,headers:{...route.request().headers(),'x-user-role':internalRole}});await route.fulfill({response:r});});
  try{
    await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});
    assert.equal(await page.getByRole('button',{name:'登记回标',exact:true}).count(),0);
    const row=page.locator('.el-table__row').filter({hasText:rfq.title});await row.getByRole('button',{name:'发布',exact:true}).click();await page.locator('.el-message-box').getByRole('button',{name:'确定',exact:true}).click();await page.waitForTimeout(500);
    for(let i=0;i<2;i++){
      await page.goto('http://localhost:8080/supplier',{waitUntil:'networkidle'});
      assert.equal(await page.locator('.sidebar').count(),0);
      await page.locator('.login-card input').nth(0).fill(`ui-${tag}-${i}`);await page.locator('.login-card input').nth(1).fill('Ui-test-password-123!');await page.getByRole('button',{name:'登录',exact:true}).click();
      await page.getByRole('button',{name:'查看 / 报价',exact:true}).click();const dialog=page.locator('.el-dialog:visible');
      await dialog.getByText('spec.txt',{exact:true}).waitFor();
      const specificationDownload=page.waitForEvent('download');await dialog.getByRole('button',{name:'spec.txt',exact:true}).click();assert.equal((await specificationDownload).suggestedFilename(),'spec.txt');
      await dialog.locator('input[type=file]').setInputFiles({name:`bid-${i}.txt`,mimeType:'text/plain',buffer:Buffer.from(`supplier bid ${i}`)});
      await dialog.getByRole('button',{name:`bid-${i}.txt`,exact:true}).waitFor();
      await dialog.locator('.el-table .el-input-number input').nth(0).fill(String(100+i*5));
      await dialog.getByRole('button',{name:'确认提交报价',exact:true}).click();await page.locator('.el-message-box').getByRole('button',{name:'确定',exact:true}).click();
      await dialog.waitFor({state:'hidden'});await page.getByRole('tab',{name:'报价历史',exact:true}).click();await page.getByRole('button',{name:'查看报价',exact:true}).waitFor();
      await page.getByRole('button',{name:'查看报价',exact:true}).click();await dialog.getByRole('button',{name:`bid-${i}.txt`,exact:true}).waitFor();assert.equal(await dialog.getByRole('button',{name:'上传报价附件',exact:true}).count(),0);await dialog.getByRole('button',{name:'关闭',exact:true}).click();
      await page.getByRole('button',{name:'退出登录',exact:true}).click();await page.locator('.login-card').waitFor({state:'visible'});
    }
    await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});await row.getByRole('button',{name:'2/3',exact:true}).click();
    const detail=page.locator('.el-dialog:visible');await detail.waitFor({state:'visible'});assert.equal(await detail.getByText('已回标',{exact:true}).count(),2);assert.equal(await detail.getByText('待回标',{exact:true}).count(),1);
    await detail.locator('.el-table__expand-icon').first().click();await detail.getByText('精密轴',{exact:true}).waitFor();const bidDownload=page.waitForEvent('download');await detail.getByRole('button',{name:'bid-0.txt',exact:true}).click();assert.equal((await bidDownload).suggestedFilename(),'bid-0.txt');await page.screenshot({path:'/tmp/pebs-rfq-auto-bids.png',fullPage:true});
    await page.goto('http://localhost:8080/mail-settings',{waitUntil:'networkidle'});await page.getByRole('button',{name:'保存配置',exact:true}).click();await page.getByText('邮件设置已保存',{exact:true}).waitFor();
    await page.goto('http://localhost:8080/supplier-accounts',{waitUntil:'networkidle'});
    assert(page.url().endsWith('/suppliers'));assert.equal(await page.getByRole('button',{name:'供应商账号与登录网址',exact:true}).count(),0);
    assert.equal(await page.locator('nav a[href="/supplier-accounts"]').count(),0);
    internalRole='admin';await page.reload({waitUntil:'networkidle'});
    await page.getByRole('button',{name:'供应商账号与登录网址',exact:true}).click();
    await page.getByText('供应商登录网址：',{exact:false}).waitFor();
    await page.getByRole('button',{name:'新增供应商账号',exact:true}).click();assert(await page.locator('.el-dialog:visible').count());
    assert.deepEqual(errors,[]);console.log('PASS: supplier login, two automatic bids, 2/3 indicator, bid details, attachment visibility, history, logout, mail settings and accounts UI');
  }finally{await browser.close();await api.dispose();}
})().catch(e=>{console.error(e);process.exit(1);});
