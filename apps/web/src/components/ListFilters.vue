<template>
  <section v-if="choices.length" class="combined-filter">
    <div class="filter-heading"><strong>组合查询</strong><el-select v-model="resource" size="small" @change="switchResource"><el-option v-for="s in choices" :key="s.resource" :value="s.resource" :label="s.label"/></el-select><span>所有条件同时满足；区间请添加上下限</span></div>
    <div v-for="(row,index) in rows" :key="index" class="filter-condition">
      <el-select v-model="row.field" filterable placeholder="选择字段" size="small" @change="fieldChanged(row)"><el-option v-for="f in fields" :key="f.name" :value="f.name" :label="f.label"/></el-select>
      <el-select v-model="row.op" size="small"><el-option v-for="o in operators(row)" :key="o.value" :value="o.value" :label="o.label"/></el-select>
      <el-select v-if="kind(row)==='boolean'" v-model="row.value" size="small"><el-option :value="true" label="是"/><el-option :value="false" label="否"/></el-select>
      <el-date-picker v-else-if="['date','datetime'].includes(kind(row))" v-model="row.value" :type="kind(row)" :value-format="kind(row)==='date'?'yyyy-MM-dd':`yyyy-MM-dd'T'HH:mm:ss`" size="small" placeholder="选择日期/时间"/>
      <el-input-number v-else-if="kind(row)==='number'" v-model="row.value" :controls="false" size="small"/>
      <el-select v-else-if="field(row).options&&field(row).options.length" v-model="row.value" filterable allow-create default-first-option size="small" placeholder="选择或输入状态值"><el-option v-for="o in field(row).options" :key="o.value" :value="o.value" :label="o.label"/></el-select>
      <el-input v-else v-model="row.value" maxlength="300" size="small" placeholder="输入查询值" @keyup.enter.native="apply"/>
      <el-button type="text" class="danger-link" @click="rows.splice(index,1)">删除条件</el-button>
    </div>
    <div><el-button size="small" :disabled="rows.length>=12" @click="add">添加条件</el-button><el-button size="small" type="primary" @click="apply">组合查询</el-button><el-button size="small" @click="reset">清空条件</el-button><small v-if="applied"> 已应用 {{applied}} 项条件</small></div>
  </section>
</template>
<script>
import {api, listQueryFilters} from '../api/client';
export const pageResources = {'/orders':['orders'],'/rfqs':['rfqs'],'/requisitions':['requisitions'],'/contracts':['contracts'],'/suppliers':['suppliers'],'/factories':['factories'],'/fulfillment':['receipts','inspections','returns'],'/settlements':['reconciliations','invoices','payments'],'/materials':['material-categories','materials','supplier-category-links'],'/personnel':['staff-users','buyer-authorizations'],'/forecast':['forecasts'],'/sourcing':['sourcing-projects'],'/routing':['routing-plans'],'/reports':['reports','audit-logs'],'/templates':['templates'],'/data-sources':['data-connectors'],'/workflows':['workflows','workflow-runs','notification-outbox']};
export default {
  props:{onlyResources:Array,providedSchemas:Array},
  data:()=>({schemas:[],resource:'',rows:[],applied:0}),
  computed:{choices(){return (this.onlyResources||pageResources[this.$route.path]||[]).map(r=>this.schemas.find(s=>s.resource===r)).filter(Boolean);},fields(){return this.schemas.find(s=>s.resource===this.resource)?.fields||[];}},
  async created(){try{this.schemas=this.providedSchemas||(await api.get('/list-filter-schema')).data;this.resource=this.choices[0]?.resource||'';this.rows=JSON.parse(JSON.stringify(listQueryFilters[this.resource]||[]));this.applied=this.rows.length;}catch(_){this.$message.error('组合查询字段加载失败');}},
  watch:{'$route.path'(){Object.keys(listQueryFilters).forEach(k=>delete listQueryFilters[k]);this.resource=this.choices[0]?.resource||'';this.rows=[];this.applied=0;}},
  methods:{field(row){return this.fields.find(f=>f.name===row.field)||{};},kind(row){return this.field(row).type||'text';},operators(row){return [{value:'eq',label:'等于'},{value:'ne',label:'不等于'},...(this.kind(row)==='text'?[{value:'contains',label:'包含'}]:this.kind(row)==='boolean'?[]:[{value:'gte',label:'大于等于'},{value:'lte',label:'小于等于'}])];},fieldChanged(row){row.op=this.kind(row)==='text'?'contains':'eq';row.value=this.kind(row)==='boolean'?true:this.kind(row)==='number'?0:'';},add(){const row={field:this.fields[0]?.name||'',op:'contains',value:''};this.fieldChanged(row);this.rows.push(row);},switchResource(){this.rows=JSON.parse(JSON.stringify(listQueryFilters[this.resource]||[]));this.applied=this.rows.length;this.$emit('query',this.resource);},apply(){if(this.rows.some(r=>!r.field||r.value===''||r.value===null||r.value===undefined))return this.$message.warning('请填写完整查询条件');listQueryFilters[this.resource]=JSON.parse(JSON.stringify(this.rows));this.applied=this.rows.length;this.$emit('query',this.resource);},reset(){delete listQueryFilters[this.resource];this.rows=[];this.applied=0;this.$emit('query',this.resource);}}
};
</script>
