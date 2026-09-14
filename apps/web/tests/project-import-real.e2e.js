/* eslint-env node */
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:18003/api/v1';
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/v1/**',async r=>{const u=new URL(r.request().url());await r.fulfill({response:await r.fetch({url:'http://127.0.0.1:18003'+u.pathname+u.search})});});
 const tag='IMPORT-'+Date.now();const text='项目名称：真实导入验收\n合同金额：500000元\n交付：2026年12月01日完成设备交付\n验收：交付后30天验收';
 try{
  await page.goto('http://localhost:8080/projects',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'邮件 / 合同导入',exact:true}).click();const dialog=page.getByRole('dialog',{name:'项目资料识别与草案预览',exact:true});
  await dialog.locator('textarea').fill(text);await dialog.getByRole('button',{name:'识别并预览',exact:true}).click();await dialog.getByText('项目名称候选：真实导入验收',{exact:true}).waitFor();
  assert(await dialog.getByRole('button',{name:'使用草稿并完善'}).isDisabled());await dialog.locator('.el-checkbox').click();await dialog.getByRole('button',{name:'使用草稿并完善'}).click();
  const editor=page.getByRole('dialog',{name:'项目与计划',exact:true});const field=label=>editor.locator('.el-form-item').filter({has:page.locator('.el-form-item__label',{hasText:label})}).locator('input').first();await field('项目编号').fill(tag);await editor.getByRole('button',{name:'保存项目',exact:true}).click();
  await page.reload({waitUntil:'networkidle'});await page.locator('.el-table__row').filter({hasText:tag}).getByRole('button',{name:'编辑 / 甘特图'}).click();await editor.getByText('导入来源与待确认项',{exact:true}).click();await editor.locator('pre').getByText('合同金额：500000元',{exact:false}).waitFor();await editor.getByRole('button',{name:'取消',exact:true}).click();
  const response=await fetch(base+'/projects?keyword='+tag,{headers:{'X-User-Role':'procurement_manager'}});const saved=(await response.json()).items[0];assert.equal(saved.budget,0);assert.equal(saved.status,'draft');assert.equal(saved.import_evidence.source_text,text);assert.equal(saved.tasks[1].finish,null);
  await page.getByRole('button',{name:'邮件 / 合同导入',exact:true}).click();await dialog.locator('textarea').fill(text);await dialog.getByRole('button',{name:'识别并预览',exact:true}).click();await dialog.getByText('发现相同文本已用于项目：',{exact:false}).waitFor();
  await dialog.getByRole('tab',{name:'上传邮件 / Word文件'}).click();
  const eml=Buffer.from('MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\nSubject: Import\r\n\r\n'+text);
  await dialog.locator('input[type=file]').setInputFiles({name:'project.eml',mimeType:'message/rfc822',buffer:eml});await dialog.getByRole('button',{name:'识别并预览',exact:true}).click();await dialog.getByText('项目名称候选：真实导入验收',{exact:true}).waitFor();
  const docx=execFileSync('../api/.venv/bin/python',['-c',"import io,sys; from docx import Document; d=Document(); d.add_paragraph('项目名称：Word导入验收'); d.add_paragraph('交付：2026年12月01日完成设备交付'); b=io.BytesIO(); d.save(b); sys.stdout.buffer.write(b.getvalue())"]);
  await dialog.locator('input[type=file]').setInputFiles({name:'contract.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:docx});await dialog.getByRole('button',{name:'识别并预览',exact:true}).click();await dialog.getByText('项目名称候选：Word导入验收',{exact:true}).waitFor();assert.deepEqual(errors,[]);
  console.log('PASS real operator: text preview/confirmation/save/reload/source evidence/duplicate detection and EML/DOCX upload; no mocked responses');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
