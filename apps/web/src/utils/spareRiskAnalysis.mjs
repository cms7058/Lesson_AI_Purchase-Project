// Scenario exploration only: coefficients are explicit teaching assumptions, not fitted data.
export function analyzeSpareRisk(equipment, costs) {
  const latest = key => Number(equipment.history[key].slice(-1)[0][1]);
  const capability = equipment.history.capability.slice(-1)[0];
  const base = equipment.quantity[0].value;
  const stock = -equipment.quantity[3].value;
  const currentQuantity = equipment.quantity[4].value;
  const risk = 1 + equipment.quantity[1].value / base;
  const load = 1 + equipment.quantity[2].value / (base * risk);
  const names = ['OEE', 'MTBF', 'MTTR', 'Cp', 'Cpk', '订单负荷'];
  const values = [latest('oee'), latest('mtbf'), latest('mttr'), Number(capability[1]), Number(capability[2]), load];
  const total = equipment.contributions.slice(0, 5).reduce((a, b) => a + b, 0);
  const factors = names.map((name, i) => ({ name, current: values[i], low: values[i] * .9, high: i === 0 ? Math.min(100, values[i] * 1.1) : values[i] * 1.1, weight: i < 5 ? equipment.contributions[i] / total : null, unit: ['%', 'h', 'h', '', '', '倍'][i] }));
  const predict = inputs => {
    const shifts = inputs.slice(0, 5).map((v, i) => (v / values[i] - 1) * (i === 2 ? 1 : -1));
    const riskMultiplier = Math.max(1, risk + shifts.reduce((s, v, i) => s + v * factors[i].weight, 0));
    const demand = base * riskMultiplier * inputs[5];
    return { demand, quantity: Math.max(0, Math.ceil(demand - stock - 1e-9)) };
  };
  // Same 3-point uncertainty distribution for every quantity and every DOE run.
  const costAt = (quantity, demand) => {
    const available = quantity + stock;
    let excess = 0, shortage = 0;
    [[.8, .25], [1, .5], [1.2, .25]].forEach(([multiplier, probability]) => {
      excess += Math.max(0, available - demand * multiplier) * probability;
      shortage += Math.max(0, demand * multiplier - available) * probability;
    });
    const purchase = quantity * costs.purchase;
    const holding = excess * costs.holding;
    const loss = shortage * costs.shortage;
    return { quantity, purchase, holding, loss, total: purchase + holding + loss };
  };
  const current = predict(values);
  const curve = Array.from({ length: Math.ceil(current.demand * 1.4) + 1 }, (_, quantity) => costAt(quantity, current.demand));
  const best = curve.reduce((a, b) => b.total < a.total ? b : a);
  const runs = Array.from({ length: 64 }, (_, index) => {
    const levels = factors.map((_, i) => (index >> i) & 1);
    const inputs = factors.map((f, i) => levels[i] ? f.high : f.low);
    const response = predict(inputs);
    return { id: index + 1, levels, inputs, ...response, cost: costAt(currentQuantity, response.demand).total };
  });
  const mean = rows => rows.reduce((s, r) => s + r.quantity, 0) / rows.length;
  const effects = factors.map((f, i) => {
    const low = mean(runs.filter(r => !r.levels[i]));
    const high = mean(runs.filter(r => r.levels[i]));
    const lowInput = [...values], highInput = [...values];
    lowInput[i] = f.low; highInput[i] = f.high;
    return { name: f.name, low, high, effect: high - low,
      lowCost: costAt(currentQuantity, predict(lowInput).demand).total,
      highCost: costAt(currentQuantity, predict(highInput).demand).total };
  });
  const interaction = [0, 1].map(level => [0, 1].map(loadLevel => mean(runs.filter(r => r.levels[0] === level && r.levels[5] === loadLevel))));
  return { factors, runs, effects, interaction, curve, best, current, currentCost: costAt(currentQuantity, current.demand), currentQuantity, base, stock, risk, load };
}
