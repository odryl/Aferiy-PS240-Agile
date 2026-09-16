const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../custom_components/aecc_battery/frontend/aferiy-agile-plan-card.js'), 'utf8');
const now = Date.parse('2026-09-16T13:10:00Z');
class Clock extends Date { static now() { return now; } }
function fixture() {
  let Card;
  class Element {
    attachShadow() { return { innerHTML: '', querySelectorAll: () => [], querySelector: () => null }; }
  }
  vm.runInNewContext(source, { HTMLElement: Element, Date: Clock, Intl, console,
    customElements: { define: (_, klass) => { Card = klass; } },
    window: { sessionStorage: { getItem: () => null, setItem() {} }, setInterval, clearInterval },
  });
  const card = new Card();
  const state = (entity_id, state, attributes) => ({ entity_id, state, attributes });
  const periods = [[0,4,'self_gen','standard'],[4,7,'charge','cheap'],[7,13,'self_gen','standard'],[13,16,'charge','cheap'],[16,19,'self_gen','peak'],[19,22,'self_gen','standard'],[22,24,'charge','cheap']].map(([start,end,action,band]) => ({
    start:new Date(Date.UTC(2026,8,16,start-1)).toISOString(), end:new Date(Date.UTC(2026,8,16,end-1)).toISOString(),
    local_start:`${String(start).padStart(2,'0')}:00`,local_end:`${String(end%24).padStart(2,'0')}:00`,action,cosy_rate_band:band,
    slot_target_soc:80,rate_gbp_per_kwh:band==='cheap'?.124:band==='peak'?.379:.253, cover_until:'22:00',
  }));
  const plan = { tariff_name:'Cosy Octopus',status:'proposed',date:'2026-09-16',cosy_periods:periods,reserve_soc:20,estimated_net_saving_gbp:1.18,planned_grid_charge_kwh:3.2 };
  const today=state('sensor.test_agile_proposed_plan_today','Proposed',plan);
  const tomorrow=state('sensor.test_agile_proposed_plan_tomorrow','Waiting For Rates',{tariff_name:'Cosy Octopus',status:'waiting_for_rates',reason:'Tomorrow rates not published'});
  const shadow=state('sensor.test_agile_shadow_operating_state','Cosy Solar Wait',{recommended_operating_mode:'Idle',reason:'Enough time for solar',soc_percent:62,reserve_soc:20,target_soc:80,connection_last_successful_update:new Date(now).toISOString(),connection_stale_after_seconds:90,latest_grid_charge_start:new Date(now+35*60000).toISOString()});
  const control=state('switch.test_cosy_automated_control','on',{status:'Active',active_mode:'Idle'});
  const flex=state('switch.test_cosy_daylight_flex','on',{});
  const calls=[];
  card.setConfig({});
  const hass={states:Object.fromEntries([today,tomorrow,shadow,control,flex].map(s=>[s.entity_id,s])),config:{time_zone:'Europe/London'},callService:async(...args)=>calls.push(args)};
  card.hass=hass;
  return {card,today,tomorrow,shadow,control,flex,hass,calls,html:()=>card._root.innerHTML};
}

test('shows real live SOC, active period, conditional catch-up time and target',()=>{
  const f=fixture();
  assert.match(f.html(),/Waiting for solar/);
  assert.match(f.html(),/62%/);
  assert.match(f.html(),/35 min/);
  assert.match(f.html(),/Earlier today · 3 periods/);
  assert.match(f.html(),/80%<\/strong> target by 16:00/);
  assert.equal(f.calls.length,0);
});
test('unpublished tomorrow cannot leak today costs and does not replace live battery header',()=>{
  const f=fixture();f.card._selectedDay='tomorrow';f.card._renderIfNeeded(true);
  assert.match(f.html(),/Tomorrow rates not published/);
  assert.match(f.html(),/Waiting for solar/);
  assert.doesNotMatch(f.html(),/£1.18/);
  assert.doesNotMatch(f.html(),/Earlier today/);
});
test('stale readings are never presented as live SOC or solar countdown',()=>{
  const f=fixture();f.shadow.attributes.connection_last_successful_update='2026-09-16T10:00:00Z';f.card.hass=f.hass;
  assert.match(f.html(),/Battery data unavailable/);
  assert.doesNotMatch(f.html(),/62%|35 min/);
});
test('disabled and blocked controllers are distinct from active execution',()=>{
  const f=fixture();f.control.state='off';f.card.hass=f.hass;
  assert.match(f.html(),/PROPOSED · CONTROL OFF/);
  assert.match(f.html(),/This plan is advisory/);
  f.control.state='on';f.control.attributes.status='Inhibited';f.control.attributes.reason='Connection guard';f.card.hass=f.hass;
  assert.match(f.html(),/Control inhibited/);
  assert.match(f.html(),/Connection guard/);
  assert.doesNotMatch(f.html(),/35 min/);
});
test('null prices and estimates are unavailable, zero and negative prices remain valid',()=>{
  const f=fixture();assert.equal(f.card._rate(null),'—');assert.equal(f.card._money(null),'—');assert.equal(f.card._number(null),'—');
  assert.equal(f.card._rate(0),'0.0p');assert.equal(f.card._rate(-.02),'-2.0p');
  assert.equal(f.card._cosyPeriodPrice({rate_gbp_per_kwh:null}),'—/kWh');
});
test('live SOC and decision changes trigger rendering without changing plan attributes',()=>{
  const f=fixture();f.shadow.attributes.soc_percent=65;f.card.hass=f.hass;assert.match(f.html(),/65%/);
});
test('controller service is called only on explicit action; errors restore usable controls',async()=>{
  const f=fixture();assert.equal(f.calls.length,0);
  await f.card._toggleCosySwitch(f.flex.entity_id);
  assert.equal(JSON.stringify(f.calls),JSON.stringify([['switch','turn_off',{entity_id:f.flex.entity_id}]]));
  f.hass.callService=async()=>{throw new Error('Permission denied')};
  await f.card._toggleCosySwitch(f.control.entity_id);
  assert.match(f.html(),/Control could not be changed: Permission denied/);
  assert.equal(f.card._pendingSwitches.size,0);
});
test('capacity shortfalls and untrusted entity text are safely visible',()=>{
  const f=fixture();f.today.attributes.cosy_periods[3].cover_shortfall_kwh=.85;
  f.control.attributes.reason='<img src=x onerror=alert(1)>';f.card.hass=f.hass;
  assert.match(f.html(),/Capacity shortfall 0.85 kWh/);
  assert.match(f.html(),/&lt;img/);assert.doesNotMatch(f.html(),/<img/);
});
test('Agile still renders original half-hour schedule',()=>{
  const f=fixture();f.today.attributes.slots=[{...f.today.attributes.cosy_periods[3],energy_kwh:.3}];f.today.attributes.tariff_name='Octopus Agile';f.tomorrow.attributes.tariff_name='Octopus Agile';f.card.hass=f.hass;
  assert.match(f.html(),/All half-hour Octopus Agile prices/);assert.doesNotMatch(f.html(),/co-card/);
});
test('ambiguous control discovery never picks another battery switch',()=>{
  const f=fixture();f.hass.states['switch.other_cosy_automated_control']={entity_id:'switch.other_cosy_automated_control',state:'on',attributes:{}};
  f.card.hass=f.hass;assert.equal(f.card._findSwitch(null,'_cosy_automated_control','Cosy Automated Control').entity_id,f.control.entity_id);
  f.card.setConfig({cosy_control_entity:'switch.missing'});assert.match(f.html(),/Control unavailable/);
});
module.exports={fixture};
