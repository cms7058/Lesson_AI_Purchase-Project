/* eslint-env node */
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));try{
 await page.goto('http://localhost:8080/procurement-dashboard',{waitUntil:'networkidle'});await page.waitForFunction(()=>document.querySelector('.cockpit')?.__vue__?.monthData?.kpis);
 assert.equal(await page.locator('.sidebar a[href="/assistant"]').count(),0);
 await page.locator('.cockpit').evaluate(el=>{const v=el.__vue__;v.selectMonth({name:v.overview.trend[0].name});});await page.waitForFunction(()=>!document.querySelector('.cockpit').__vue__.loading);
 const before=await page.locator('.cockpit').evaluate(el=>el.__vue__.buyerPie.series[0].data);
 await page.locator('.cockpit').evaluate(el=>{const v=el.__vue__,b=v.buyerPie.series[0].data[0];v.selectBuyerPie({data:b,name:b.name});});await page.waitForFunction(()=>!document.querySelector('.cockpit').__vue__.loading);
 assert.deepEqual(await page.locator('.cockpit').evaluate(el=>el.__vue__.buyerPie.series[0].data),before);
 assert(await page.locator('.cockpit').evaluate(el=>el.__vue__.buyerTimeline.every(r=>r.buyer_id===el.__vue__.buyer)));
 // Isolated UI fixture verifies drill navigation independently of local demo master data.
 await page.locator('.cockpit').evaluate(el=>{const v=el.__vue__;v.monthData.category_amount=[{key:'a',name:'一级',level:1,parent_id:null,value:50},{key:'b',name:'二级',level:2,parent_id:'a',value:50},{key:'c',name:'三级',level:3,parent_id:'b',value:50}];v.drillCategory({data:v.categoryRows[0]});});
 assert.equal(await page.locator('.cockpit').evaluate(el=>el.__vue__.categoryRows[0].level),2);
 await page.locator('.cockpit').evaluate(el=>el.__vue__.drillCategory({data:el.__vue__.categoryRows[0]}));assert.equal(await page.locator('.cockpit').evaluate(el=>el.__vue__.categoryRows[0].level),3);
 await page.getByRole('button',{name:'返回上级',exact:true}).click();assert.equal(await page.locator('.cockpit').evaluate(el=>el.__vue__.categoryRows[0].level),2);
 await page.locator('.ai-fab').click();const dialog=page.locator('.assistant-dialog');
 for(const question of ['你好','TOC是什么，如何计算？','请帮我看看采购订单','其中待送货的有哪些']){
  await dialog.locator('.ai-compose textarea').fill(question);const response=page.waitForResponse(r=>r.url().endsWith('/assistant/chat'));await dialog.getByRole('button',{name:'发送',exact:true}).click();const data=await (await response).json();assert(data.message.length>15);await page.waitForFunction(()=>!document.querySelector('.assistant-dialog .ai-chat').__vue__.sending);
 }
 const last=await dialog.locator('.ai-message').last().innerText();assert(last.includes('待送货')||last.includes('supplier_confirmed'));
 await page.screenshot({path:'/tmp/pebs-free-chat.png'});assert.deepEqual(errors,[]);console.log('PASS: stable buyer pie, selected 3D data, three-level drill/back, removed menu, typed conversation and contextual followup');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
