<template><div><div ref="canvas" style="height:460px;width:100%"/><el-alert v-if="error" title="当前浏览器无法绘制三维视图，请启用硬件加速；下方仍可查看相同数据。" type="warning" :closable="false"/><el-collapse><el-collapse-item title="查看三维图表数据"><el-table :data="rows.slice((page-1)*10,page*10)" size="small"><el-table-column prop="month" label="月份"/><el-table-column prop="buyer_name" label="采购员"/><el-table-column prop="amount" :label="'订单金额 '+currency"/></el-table><el-pagination :current-page.sync="page" :page-size="10" :total="rows.length" layout="total, prev, pager, next"/></el-collapse-item></el-collapse></div></template>
<script>
import * as echarts from 'echarts';
import 'echarts-gl';
export default {
 props:{rows:{type:Array,default:()=>[]},currency:String,buyer:String},data:()=>({error:false,page:1}),
 mounted(){try{this.chart=echarts.init(this.$refs.canvas);this.chart.on('click',e=>{if(e.data&&e.data.buyer_id)this.$emit('select',{key:e.data.buyer_id,name:e.data.buyer_name});});this.draw();this.observer=new ResizeObserver(()=>this.chart&&this.chart.resize());this.observer.observe(this.$refs.canvas);}catch(_){this.error=true;}},
 beforeDestroy(){if(this.observer)this.observer.disconnect();if(this.chart)this.chart.dispose();},
 watch:{rows(){this.page=1;this.draw();},buyer(){this.draw();},currency(){this.draw();}},
 methods:{draw(){if(!this.chart)return;const months=[...new Set(this.rows.map(r=>r.month))];const buyers=[...new Set(this.rows.map(r=>r.buyer_id))];const names=buyers.map(id=>this.rows.find(r=>r.buyer_id===id).buyer_name);try{this.chart.setOption({tooltip:{formatter:p=>`${p.data.month}<br/>${echarts.format.encodeHTML(p.data.buyer_name)}<br/>${this.currency} ${Number(p.data.amount).toLocaleString()}`},xAxis3D:{type:'category',name:'月份',data:months},yAxis3D:{type:'category',name:'采购员',data:names},zAxis3D:{type:'value',name:'金额 '+this.currency},grid3D:{boxWidth:180,boxDepth:90,viewControl:{alpha:25,beta:35,distance:260},light:{main:{intensity:1.2},ambient:{intensity:.5}}},series:[{type:'bar3D',shading:'lambert',data:this.rows.map(r=>({...r,value:[months.indexOf(r.month),buyers.indexOf(r.buyer_id),r.amount],itemStyle:{color:this.buyer&&r.buyer_id!==this.buyer?'#cbd5e1':'#2878ff',opacity:this.buyer&&r.buyer_id!==this.buyer?.3:1}}))}]},true);this.error=false;}catch(_){this.error=true;}}}
};
</script>
