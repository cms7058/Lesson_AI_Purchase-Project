import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { analyzeSpareRisk } from '../src/utils/spareRiskAnalysis.mjs';
const source = fs.readFileSync(new URL('../src/views/EquipmentSpareRisk.vue', import.meta.url), 'utf8');
const equipment = vm.runInNewContext(source.slice(source.indexOf('const demo ='), source.indexOf('export default')) + '\ndemo;');
const costs = { purchase: 200, holding: 20, shortage: 1500 };
for (const item of equipment) {
  test(item.code + ': baseline, balanced DOE, costs and sensitivity', () => {
    const a = analyzeSpareRisk(item, costs);
    assert.equal(a.current.quantity, item.quantity[4].value);
    assert.equal(a.runs.length, 64);
    assert.equal(new Set(a.runs.map(r => r.levels.join(''))).size, 64);
    for (let i = 0; i < 6; i++) assert.equal(a.runs.filter(r => r.levels[i]).length, 32);
    for (const i of [0, 1, 3, 4]) assert.ok(a.effects[i].effect <= 0);
    for (const i of [2, 5]) assert.ok(a.effects[i].effect > 0);
    assert.ok(Math.abs(a.factors.slice(0, 5).reduce((s, f) => s + f.weight, 0) - 1) < 1e-10);
    assert.ok(a.curve.every(r => Number.isFinite(r.total) && r.total >= a.best.total));
    assert.equal(a.currentCost.total, a.currentCost.purchase + a.currentCost.holding + a.currentCost.loss);
    const expensiveShortage = analyzeSpareRisk(item, { ...costs, shortage: 100000 });
    assert.ok(expensiveShortage.best.quantity >= a.best.quantity);
    const expensivePurchase = analyzeSpareRisk(item, { ...costs, purchase: 100000 });
    assert.equal(expensivePurchase.best.quantity, 0);
    assert.ok(a.runs.every(r => Number.isInteger(r.quantity) && r.quantity >= 0));
  });
}
