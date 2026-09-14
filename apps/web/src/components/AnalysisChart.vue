<template><div ref="canvas" style="height:320px;width:100%"></div></template>
<script>
import * as echarts from 'echarts';
export default {props:{option:Object},mounted(){this.chart=echarts.init(this.$refs.canvas);this.chart.on('click',event=>this.$emit('select',event));this.draw();if(window.ResizeObserver){this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(this.$refs.canvas);}window.addEventListener('resize',this.resize);},beforeDestroy(){if(this.observer)this.observer.disconnect();window.removeEventListener('resize',this.resize);if(this.chart)this.chart.dispose();},watch:{option:{deep:true,handler(){this.draw();}}},methods:{draw(){if(this.chart&&this.option)this.chart.setOption(this.option,true);},resize(){if(this.chart)this.chart.resize();}}};
</script>
