/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let imported=false;
 try{
  // Read existing RFQ data; mock import writes so this UI test never changes live records.
  await page.route('**/data-connectors?*',r=>r.fulfill({json:{items:[{id:'qa-source',name:'QA MES',connector_type:'mes',status:'active'}],total:1}}));
  await page.route('**/data-connectors/qa-source/feedback-import',r=>{imported=true;return r.fulfill({json:{inserted:1,skipped:0}});});
  await page.goto('http://localhost:8080/rfqs',{waitUntil:'networkidle'});
  await page.locator('.el-table__row').filter({hasText:'DEMO-XJ-001'}).getByRole('button',{name:'定标',exact:true}).click();
  await page.getByText('2. TOC分析定标',{exact:true}).click();
  const collection=page.locator('.toc-collection');await collection.waitFor();
  const download=page.waitForEvent('download');await collection.getByRole('button',{name:'下载采集模板',exact:true}).click();
  assert.equal((await download).suggestedFilename(),'toc-feedback-template.csv');
  await collection.getByRole('button',{name:'导入采集数据',exact:true}).click();
  const dialog=page.locator('.el-dialog:visible').last();
  await dialog.getByRole('button',{name:'校验并导入'}).click();
  await dialog.getByText('请选择不超过5MB的CSV文件',{exact:true}).waitFor();
  await dialog.locator('.el-select').click();await page.locator('.el-select-dropdown:visible').getByText('QA MES · mes',{exact:true}).click();
  await dialog.locator('input[type=file]').setInputFiles({name:'toc.csv',mimeType:'text/csv',buffer:Buffer.from('external_id\nQA-1\n')});
  await dialog.getByRole('button',{name:'校验并导入'}).click();
  await dialog.getByText(/导入成功：新增 1 条/).waitFor();assert(imported);
  await dialog.getByRole('button',{name:'关闭',exact:true}).click();
  await collection.getByRole('button',{name:'配置来源系统 API'}).click();
  await page.waitForURL('**/data-sources?setup=toc-api');
  const setup=page.locator('.el-dialog:visible').last();
  await setup.getByText('TOC接入：保存后启用连接器', {exact:false}).waitFor();
  assert.equal(await setup.locator('input').first().inputValue(),'TOC 供货反馈接口');
  assert.deepEqual(errors,[]);console.log('PASS: template download, CSV import validation/submission, TOC refresh, API setup navigation (writes mocked)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
