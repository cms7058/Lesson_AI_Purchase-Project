<template>
  <main class="learning-home">
    <header class="home-nav">
      <router-link class="home-brand" to="/">
        <BrandMark />
        <span><strong>AI助力</strong><small>智能项目与采购教学平台</small></span>
      </router-link>
      <nav aria-label="首页导航">
        <a href="#learning-path">学习路线</a>
        <a href="#capabilities">亮点能力</a>
        <router-link class="nav-entry" to="/procurement-dashboard">进入平台</router-link>
      </nav>
    </header>

    <section class="hero">
      <div class="hero-copy">
        <p class="hero-kicker">AI + 项目管理 + 智能采购</p>
        <h1>在一套完整业务闭环里，<br><em>体验AI如何助力决策</em></h1>
        <p class="hero-lead">
          面向课堂教学与实训，覆盖项目计划、采购申请、询报价、订单履约、MRO、库存与供应商分析。用演示数据完成一次可解释、可追溯的采购决策。
        </p>
        <div class="hero-actions">
          <router-link class="primary-entry" to="/procurement-dashboard">开始采购实训 <span>→</span></router-link>
          <router-link class="secondary-entry" to="/project-dashboard">进入项目管理</router-link>
          <router-link class="text-entry" to="/supplier">体验供应商端</router-link>
        </div>
        <p class="demo-note">教学演示环境 · 数据仅用于学习 · 不构成真实采购决策</p>
      </div>
      <div class="hero-visual" aria-label="AI采购决策流程示意">
        <div class="signal-grid"></div>
        <div class="flow-card source-card"><span>01</span><strong>业务数据</strong><small>订单 · 报价 · 质量</small></div>
        <div class="flow-card model-card"><span>02</span><strong>AI决策模型</strong><small>DOE验证 · TOC回归</small></div>
        <div class="flow-card result-card"><span>03</span><strong>行动建议</strong><small>比价 · 路径 · 预警</small></div>
        <div class="flow-line line-one"></div>
        <div class="flow-line line-two"></div>
        <div class="model-orbit"><i></i><i></i><i></i><b>AI</b></div>
        <div class="metric-badge"><strong>6</strong><span>业务因子</span></div>
        <div class="metric-badge second"><strong>30</strong><span>DOE试验</span></div>
      </div>
    </section>

    <section id="capabilities" class="section-block">
      <div class="section-heading"><p>核心体验</p><h2>把专业采购方法变成可操作的学习场景</h2></div>
      <div class="capability-grid">
        <article v-for="item in capabilities" :key="item.title" class="capability-card">
          <div :class="['card-icon', item.tone]">{{ item.icon }}</div>
          <h3>{{ item.title }}</h3><p>{{ item.description }}</p>
          <router-link :to="item.path">进入体验 →</router-link>
        </article>
      </div>
    </section>

    <section id="learning-path" class="learning-path section-block">
      <div class="path-copy">
        <p class="section-label">建议学习路线</p>
        <h2>从业务数据到AI决策，完成一次采购闭环</h2>
        <p>每一步都提供演示数据、分析图表与可追溯结果，适合教师讲解、学员分组操作和课后复盘。</p>
        <router-link to="/requisitions">从采购申请开始 →</router-link>
      </div>
      <ol class="path-steps">
        <li v-for="(step, index) in steps" :key="step.title">
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          <div><strong>{{ step.title }}</strong><small>{{ step.text }}</small></div>
        </li>
      </ol>
    </section>

    <footer><span>AI助力 · 智能项目与采购教学平台</span><span>教学演示版本</span></footer>
  </main>
</template>

<script>
import BrandMark from "../components/BrandMark.vue";

export default {
  name: "LearningHome",
  components: { BrandMark },
  data: () => ({
    capabilities: [
      { icon: "∑", tone: "cyan", title: "DOE + TOC 定标", description: "验证价格、交期、响应与质量因子的有效性，解释综合采购成本。", path: "/rfqs" },
      { icon: "⌘", tone: "blue", title: "多工厂供货路径", description: "比较运输成本、交期和产能约束，体验路径优化与方案权衡。", path: "/routing" },
      { icon: "▧", tone: "violet", title: "报价单智能识别", description: "上传报价文件，识别结构化字段并进入自动比价和询价闭环。", path: "/rfqs" },
      { icon: "✦", tone: "amber", title: "AI对话查数", description: "用自然语言查询订单、供应商、物料和项目，并生成图表与报告。", path: "/assistant" },
    ],
    steps: [
      { title: "认识主数据", text: "物料、供应商、人员与设备" },
      { title: "发起采购", text: "需求、寻源、询价与报价" },
      { title: "辅助定标", text: "DOE验证、TOC成本与风险" },
      { title: "跟踪复盘", text: "订单履约、质量、库存和报告" },
    ],
  }),
};
</script>

<style scoped>
.learning-home{min-height:100vh;color:#dcecff;background:#06111f;font-family:"Inter","PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}.home-nav{height:76px;max-width:1240px;margin:auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;position:relative;z-index:3}.home-brand{display:flex;align-items:center;gap:12px;color:inherit;text-decoration:none}.home-brand .brand-mark{width:42px;height:42px}.home-brand span{display:flex;flex-direction:column}.home-brand strong{font-size:20px;letter-spacing:1px}.home-brand small{font-size:11px;color:#7892ad;margin-top:3px}.home-nav nav{display:flex;align-items:center;gap:28px}.home-nav nav a{color:#9ab0c7;text-decoration:none;font-size:14px}.home-nav nav a:hover{color:#67e8f9}.home-nav .nav-entry{padding:10px 18px;border:1px solid #2b76aa;border-radius:8px;color:#e9f8ff}.hero{max-width:1240px;min-height:610px;margin:auto;padding:70px 28px 80px;display:grid;grid-template-columns:1.05fr .95fr;gap:64px;align-items:center;position:relative}.hero:before{content:"";position:absolute;width:700px;height:700px;right:-300px;top:-180px;border-radius:50%;background:radial-gradient(circle,rgba(10,145,196,.18),transparent 68%)}.hero-kicker,.section-heading p,.section-label{color:#55d8ed;font-size:13px;font-weight:700;letter-spacing:3px;text-transform:uppercase}.hero h1{font-size:52px;line-height:1.2;letter-spacing:-2px;margin:18px 0 24px;color:#f4fbff}.hero h1 em{font-style:normal;color:#62dcf5}.hero-lead{max-width:650px;color:#96abc1;font-size:17px;line-height:1.9}.hero-actions{display:flex;align-items:center;gap:14px;margin-top:34px;flex-wrap:wrap}.hero-actions a{text-decoration:none}.primary-entry{background:linear-gradient(135deg,#2b8bff,#37d6e8);color:white;padding:14px 22px;border-radius:9px;font-weight:700;box-shadow:0 14px 34px rgba(29,143,219,.24)}.primary-entry span{margin-left:16px}.secondary-entry{border:1px solid #294765;color:#dcecff;padding:13px 20px;border-radius:9px}.text-entry{color:#7dd9eb;padding:12px}.demo-note{color:#566f89;font-size:12px;margin-top:24px}.hero-visual{height:430px;position:relative;border:1px solid rgba(64,170,215,.25);border-radius:24px;background:linear-gradient(145deg,rgba(13,41,68,.86),rgba(4,20,36,.74));box-shadow:inset 0 0 50px rgba(27,102,145,.08),0 25px 80px rgba(0,0,0,.3)}.signal-grid{position:absolute;inset:0;opacity:.16;background-image:linear-gradient(#4a9cc6 1px,transparent 1px),linear-gradient(90deg,#4a9cc6 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,black,transparent)}.flow-card{position:absolute;width:150px;padding:14px 16px;border:1px solid rgba(99,210,240,.3);border-radius:12px;background:rgba(8,30,50,.92);box-shadow:0 12px 30px rgba(0,0,0,.25);z-index:2}.flow-card span{font-size:10px;color:#52cfe5}.flow-card strong,.flow-card small{display:block}.flow-card strong{margin:6px 0;font-size:14px}.flow-card small{font-size:11px;color:#7592aa}.source-card{left:26px;top:58px}.model-card{right:26px;top:58px}.result-card{right:55px;bottom:46px}.flow-line{position:absolute;height:1px;background:linear-gradient(90deg,#2a6384,#56dbee);transform-origin:left}.line-one{width:165px;left:166px;top:130px;transform:rotate(23deg)}.line-two{width:168px;left:225px;top:232px;transform:rotate(30deg)}.model-orbit{position:absolute;left:50%;top:51%;width:130px;height:130px;transform:translate(-50%,-50%);border:1px solid #247ba4;border-radius:50%;box-shadow:0 0 45px rgba(48,196,229,.2)}.model-orbit:before,.model-orbit:after{content:"";position:absolute;border:1px dashed #1e5d7d;border-radius:50%}.model-orbit:before{inset:14px}.model-orbit:after{inset:30px}.model-orbit b{position:absolute;inset:43px;display:grid;place-items:center;background:linear-gradient(135deg,#2185d3,#4be0e7);border-radius:50%;font-size:20px;color:white}.model-orbit i{position:absolute;width:8px;height:8px;background:#8cf3ff;border-radius:50%;box-shadow:0 0 12px #5de8f5}.model-orbit i:nth-child(1){top:7px;left:34px}.model-orbit i:nth-child(2){right:1px;top:70px}.model-orbit i:nth-child(3){bottom:5px;left:28px}.metric-badge{position:absolute;left:28px;bottom:50px;display:flex;align-items:center;gap:8px;color:#7490aa}.metric-badge strong{font-size:27px;color:#dffbff}.metric-badge span{font-size:11px}.metric-badge.second{left:116px}.section-block{max-width:1240px;margin:auto;padding:92px 28px}.section-heading{max-width:700px}.section-heading h2,.learning-path h2{font-size:34px;margin:12px 0 38px;color:#f1f8ff}.capability-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}.capability-card{padding:28px 24px;border:1px solid #17324c;border-radius:16px;background:linear-gradient(155deg,#0b2036,#081726);transition:.25s}.capability-card:hover{transform:translateY(-5px);border-color:#2a7196}.card-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:11px;font-size:21px}.cyan{color:#76ecf4;background:#0c3e4c}.blue{color:#72afff;background:#102d54}.violet{color:#c3a2ff;background:#2a214a}.amber{color:#ffd17a;background:#463516}.capability-card h3{margin:20px 0 10px;font-size:17px}.capability-card p{min-height:68px;color:#7f98af;line-height:1.7;font-size:13px}.capability-card a,.path-copy a{color:#55d8ed;text-decoration:none;font-size:13px}.learning-path{display:grid;grid-template-columns:.9fr 1.1fr;gap:90px;align-items:center;border-top:1px solid #112b43}.path-copy>p:not(.section-label){color:#8199b0;line-height:1.8}.path-copy a{display:inline-block;margin-top:18px}.path-steps{list-style:none;padding:0;margin:0}.path-steps li{display:flex;gap:18px;align-items:center;padding:20px 0;border-bottom:1px solid #183149}.path-steps li>span{width:42px;color:#46ccdf;font-family:monospace;font-size:17px}.path-steps div{display:flex;justify-content:space-between;gap:20px;flex:1}.path-steps strong{font-size:15px}.path-steps small{color:#718aa2}footer{max-width:1184px;margin:auto;padding:28px 0 40px;border-top:1px solid #142c43;display:flex;justify-content:space-between;color:#557089;font-size:12px}@media(max-width:900px){.home-nav nav>a:not(.nav-entry){display:none}.hero{grid-template-columns:1fr;padding-top:45px}.hero h1{font-size:40px}.hero-visual{height:390px}.capability-grid{grid-template-columns:repeat(2,1fr)}.learning-path{grid-template-columns:1fr;gap:35px}}@media(max-width:560px){.home-nav{padding:0 18px}.home-brand small{display:none}.hero,.section-block{padding-left:18px;padding-right:18px}.hero h1{font-size:34px}.hero-visual{display:none}.capability-grid{grid-template-columns:1fr}.path-steps div{display:block}.path-steps small{display:block;margin-top:6px}footer{margin:0 18px}.secondary-entry,.text-entry{font-size:13px}}
</style>
