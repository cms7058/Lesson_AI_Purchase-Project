/* eslint-env node */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://localhost:8080/procurement-dashboard',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>{const v=document.querySelector('.cockpit')?.__vue__;return v&&!v.loading&&v.overview.trend?.length;});
  const months=await page.locator('.cockpit').evaluate(el=>el.__vue__.overview.trend);
  for(const m of [months[0],months[months.length-1]]){
   await page.locator('.cockpit').evaluate((el,name)=>el.__vue__.selectMonth({name}),m.name);
   await page.waitForFunction(()=>!document.querySelector('.cockpit').__vue__.loading);
   const result=await page.locator('.cockpit').evaluate(el=>el.__vue__.data);
   assert.equal(result.kpis.purchase_amount,m.value);
   assert.equal(result.material_amount.reduce((n,x)=>n+x.value,0),m.value);
   assert.equal(result.buyer_stats.reduce((n,x)=>n+x.amount,0),m.value);
   assert.equal(await page.locator('.cockpit').evaluate(el=>el.__vue__.overview.trend.length),months.length);
  }
  const three=page.locator('h3').filter({hasText:'采购员 × 时间 × 订单金额'}).locator('..');
  await three.scrollIntoViewIfNeeded();await page.waitForTimeout(1500);
  const state=await three.locator('div').first().evaluate(el=>{const v=el.__vue__;return {error:v.error,type:v.chart.getOption().series[0].type,rows:v.rows};});
  assert.equal(state.error,false);assert.equal(state.type,'bar3D');assert(state.rows.length);
  await three.locator('div').first().evaluate(el=>{const v=el.__vue__;const r=v.rows[0];v.chart.trigger('click',{data:r});});
  await page.waitForFunction(()=>{const v=document.querySelector('.cockpit').__vue__;return !v.loading&&v.buyer;});
  assert.equal(await page.locator('.cockpit').evaluate(el=>el.__vue__.buyer),state.rows[0].buyer_id);
  await three.scrollIntoViewIfNeeded();await page.waitForTimeout(800);await page.screenshot({path:'/tmp/pebs-cockpit-3d.png'});
  assert.deepEqual(errors,[]);console.log('PASS: month switching, amount reconciliation, two pies, real bar3D rendering and buyer click');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
