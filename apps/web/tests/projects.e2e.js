/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let rows=[];
 await page.route('**/api/v1/projects**',async r=>{
  const method=r.request().method();
  if(method==='POST'){const data=r.request().postDataJSON();rows=[{...data,id:'browser-test',version:1}];return r.fulfill({json:rows[0]});}
  return r.fulfill({json:{items:rows,total:rows.length}});
 });
 try{
  await page.goto('http://localhost:8080/projects',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'新建项目',exact:true}).click();
  const d=page.locator('.el-dialog:visible');
  const field=label=>d.locator('.el-form-item').filter({has:page.locator('.el-form-item__label',{hasText:label})}).locator('input').first();
  await field('项目编号').fill('P-BROWSER');await field('项目名称').fill('浏览器测试项目');
  await d.getByRole('button',{name:'增加任务'}).click();
  const task=d.locator('.el-table__row').first();await task.locator('input').first().fill('设计');
  const dates=task.locator('.el-date-editor input');
  await dates.nth(0).fill('2026-09-08');await dates.nth(0).press('Enter');
  await dates.nth(1).fill('2026-09-10');await dates.nth(1).press('Enter');
  await d.locator('.el-dialog__header').click();
  await d.getByRole('tab',{name:'项目甘特图',exact:true}).click();
  await d.locator('.project-gantt-row').waitFor();
  assert((await d.locator('.project-track>div').boundingBox()).width>0);
  await d.getByRole('button',{name:'保存项目',exact:true}).click();
  await page.locator('.el-table__row').filter({hasText:'P-BROWSER'}).waitFor();
  assert.equal(rows[0].tasks[0].name,'设计');assert.deepEqual(errors,[]);
  console.log('PASS project form, task dates, Gantt and save (writes mocked)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
