/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];const results=[];
  page.on('pageerror',e=>errors.push({path:page.url(),error:e.message}));
  page.on('console',m=>{if(m.type()==='error')errors.push({path:page.url(),error:m.text()});});
  await page.route('**/api/v1/**',async route=>{const url=new URL(route.request().url());const response=await route.fetch({url:`http://127.0.0.1:18001${url.pathname}${url.search}`});if(response.status()>=400)errors.push({api:url.pathname,status:response.status(),body:await response.text()});await route.fulfill({response});});
  const paths=['/','/assistant','/requisitions','/rfqs','/orders','/fulfillment','/settlements','/contracts','/templates','/workflows','/forecast','/sourcing','/suppliers','/materials','/personnel','/routing','/data-sources','/mail-settings','/reports'];
  async function dialogCheck(editing=false){
    const dialog=page.locator('.el-dialog:visible').last();
    await dialog.waitFor({state:'visible'});
    const box=await dialog.boundingBox();
    assert(box.x>=0 && box.x+box.width<=1441,'dialog outside viewport');
    assert(await dialog.locator('.el-dialog__footer').count(),'missing dialog footer');
    if(editing){
      const fields=dialog.locator('.el-form-item').filter({has:page.locator('.el-form-item__label',{hasText:/名称|标题|备注|说明/})}).locator('input:not([readonly]):not([disabled]),textarea:not([readonly]):not([disabled])');
      if(await fields.count()){
        const input=fields.first();const original=await input.inputValue();await input.fill(original+' QA');await input.press('Tab');
        const save=dialog.locator('.el-dialog__footer').getByRole('button',{name:/保存|更新|提交/}).first();
        if(await save.count()){
          const [response]=await Promise.all([page.waitForResponse(r=>['PATCH','PUT'].includes(r.request().method())&&r.url().includes('/api/v1/')),save.click()]);
          assert(response.ok(),'edit submission failed');await page.waitForTimeout(500);
          for(const close of await page.locator('.el-dialog:visible .el-dialog__headerbtn').all())await close.click();
          return;
        }
      }
    }
    const input=dialog.locator('textarea:not([readonly]):not([disabled]),input:not([readonly]):not([disabled]):not([type=number])').first();
    if(await input.count()){const previous=await input.inputValue();await input.fill(previous);await input.press('Tab');}
    await dialog.locator('.el-dialog__headerbtn').click();
    await dialog.waitFor({state:'hidden'});
  }
  async function inspectTab(){
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.el-loading-mask')).every(el=>getComputedStyle(el).display==='none'||el.getBoundingClientRect().height===0));
    await page.waitForTimeout(250);
    let dialogs=0;
    const edit=page.getByRole('button',{name:'编辑',exact:true}).filter({visible:true});
    for(let i=0;i<await edit.count();i++)if(await edit.nth(i).isEnabled()){await edit.nth(i).click();await dialogCheck(true);dialogs++;break;}
    const create=page.getByRole('button',{name:/^(新增|新建|录入|创建)/}).filter({visible:true});
    if(await create.count()){await create.first().click();await dialogCheck();dialogs++;}
    return dialogs;
  }
  try{
    for(const path of paths){
      await page.goto(`http://localhost:8080${path}`,{waitUntil:'networkidle'});
      assert(await page.locator('h1').count(),`${path} missing heading`);
      let dialogs=0;const tabs=await page.locator('.el-tabs__item').allTextContents();
      if(path==='/material-costs'){
        await page.getByPlaceholder('请输入物料编号').fill('DEMO-MAT-001');await page.getByRole('button',{name:'查询采购历史'}).click();await page.waitForSelector('canvas');
        const historyTabs=await page.getByRole('tab').allTextContents();
        for(const name of historyTabs){await page.getByRole('tab',{name:name.trim(),exact:true}).click();await page.waitForLoadState('networkidle');}
      } else if(tabs.length){
        for(const name of tabs){await page.locator('.el-tabs__item').filter({hasText:name.trim()}).first().click();await page.waitForLoadState('networkidle');dialogs+=await inspectTab();}
      } else dialogs+=await inspectTab();
      results.push({path,title:await page.locator('h1').first().textContent(),tabs:tabs.length,dialogs});
      console.log(JSON.stringify(results[results.length-1]));
    }
    console.log('BROWSER_ERRORS',JSON.stringify(errors));
    assert.deepEqual(errors,[]);
    console.log(`PASS ${results.length} pages; all tabs and available create/edit dialogs opened and closed`);
  }catch(error){console.log('FAILED_PAGE',page.url(),'ERRORS',JSON.stringify(errors));await page.screenshot({path:'/tmp/pebs-qa-failure.png',fullPage:true});throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
