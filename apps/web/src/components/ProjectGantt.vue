<template><section><p>拖动任务条按日历日移动，后续依赖任务联动；修改后点击“保存项目”。工期和人员请在任务明细编辑。</p><div ref="canvas" class="vtable-project-gantt" style="height:480px;width:100%;position:relative;border:1px solid #e5eaf0" aria-label="项目甘特图"/></section></template>
<script>
import {Gantt,TYPES} from '@visactor/vtable-gantt';
export default {
 props:{tasks:{type:Array,default:()=>[]},staff:{type:Array,default:()=>[]},disabled:Boolean},
 mounted(){this.render();this.observer=new ResizeObserver(()=>{if(this.$refs.canvas.clientWidth)this.render();});this.observer.observe(this.$refs.canvas);},
 beforeDestroy(){this.observer?.disconnect();this.instance?.release();},
 watch:{tasks:{deep:true,handler(){this.render();}},staff(){this.render();},disabled(){this.render();}},
 methods:{render(){
  if(!this.$refs.canvas?.clientWidth)return;
  const records=this.tasks.map(t=>{const s=this.staff.find(s=>s.id===t.owner_id);return {...t,person:s?.name||'未分配',department:s?.department||'',name:(t.parent_id?'　↳ ':'')+t.name};});
  const dates=records.flatMap(t=>[t.start,t.finish]).filter(Boolean).sort();
  const shift=(d,n)=>new Date(Date.parse(d)+n*86400000).toISOString().slice(0,10);
  const options={
   records,rowHeight:42,headerRowHeight:32,minDate:dates.length?shift(dates[0],-7):undefined,maxDate:dates.length?shift(dates[dates.length-1],8):undefined,
   taskListTable:{tableWidth:450,columns:[{field:'name',title:'任务',width:180},{field:'person',title:'负责人',width:90},{field:'department',title:'部门',width:90},{field:'start',title:'开始日期',width:105},{field:'finish',title:'结束日期',width:105},{field:'progress',title:'进度 %',width:80}]},
   taskBar:{startDateField:'start',endDateField:'finish',progressField:'progress',moveable:!this.disabled,resizable:false,progressAdjustable:false,labelText:'{name}',labelTextStyle:{color:'#fff',fontSize:13},barStyle:{barColor:'#337ecc',completedBarColor:'#16a085',cornerRadius:4}},
   dependency:{links:records.flatMap(t=>(t.predecessors||[]).map(id=>({type:TYPES.DependencyType.FinishToStart,linkedFromTaskKey:id,linkedToTaskKey:t.id}))),linkCreatable:false,linkDeletable:false},
   timelineHeader:{colWidth:36,scales:[{unit:'month',step:1,format:d=>`${d.startDate.getFullYear()}-${d.startDate.getMonth()+1}`},{unit:'day',step:1,format:d=>String(d.dateIndex)}]},grid:{weekendBackgroundColor:'#f1f5f9'},frame:{verticalSplitLineMoveable:true}
  };
  if(this.instance){this.instance.updateOption(options);return;}
  this.instance=new Gantt(this.$refs.canvas,options);
  this.instance.on('change_date_range',e=>{const day=value=>{const d=new Date(value);return Date.UTC(d.getFullYear(),d.getMonth(),d.getDate());};const days=Math.round((day(e.startDate)-day(e.oldStartDate))/86400000);if(!this.disabled&&Number.isFinite(days)&&days)this.$emit('shift',{task_id:e.record.id,days});this.$nextTick(()=>this.render());});
 }}
};
</script>
