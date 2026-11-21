const fs=require('fs'),assert=require('node:assert/strict'),{JSDOM}=require(process.env.JSDOM_PATH||'jsdom');
const dom=new JSDOM('<body></body>',{url:'https://ha.test',runScripts:'outside-only',pretendToBeVisual:true});const w=dom.window;const calls=[];
require('./studio-locale.cjs')(w);
const page={id:'fan',type:'fan',title:'Ventilátor',fan:{fanEntity:'fan.ceiling',lightEntity:'light.ceiling',speeds:[17,33,50,67,83,100].map((percentage,i)=>({label:String(i+1),percentage})),controls:{direction:true,brightness:true,temperature:true,allOff:true,timer:true},extras:[]}};
let store={version:'0.3.0',panels:[{id:'test',name:'Obývačka',paired:true,config:{theme:'cream',pages:[page]},device:{},revision:0,history:[],status:{online:true,info:{version:'Aurelvi 0.3.0'},sys:{}}}],timers:{},settings:{},latest:{},logs:[]};
const hass={language:'sk',states:{'fan.ceiling':{state:'on',attributes:{percentage:50,direction:'forward',preset_modes:['quiet','turbo']}},'light.ceiling':{state:'on',attributes:{brightness:128,color_temp_kelvin:3000}}},callWS:async msg=>{calls.push(msg);if(msg.action==='list')return structuredClone(store);if(msg.action==='save'){store.panels[0].config=structuredClone(msg.data.config);store.panels[0].device=structuredClone(msg.data.device);store.panels[0].revision++;return {revision:store.panels[0].revision};}return true;}};
w.eval(fs.readFileSync(__dirname+'/../custom_components/aurelvi/frontend/studio.js','utf8'));let studio=w.document.createElement('aurelvi-studio');studio.hass=hass;w.document.body.append(studio);
function field(label){let n=[...studio.shadowRoot.querySelectorAll('.field')].find(n=>n.querySelector('span').textContent===label);assert(n,label);return n.querySelector('input,select,textarea');}
function change(label,value){let input=field(label);if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new w.Event('change'));}
let count=0;async function test(name,fn){await fn();count++;console.log('PASS '+name);}
(async()=>{await studio.load();
await test('Studio registers as HA web component and shows panel',()=>{assert(studio.shadowRoot.textContent.includes('Obývačka'));assert(studio.shadowRoot.querySelector('iframe'));assert(calls.some(c=>c.type==='aurelvi/command'));});
await test('Studio always offers a dashboard link and protects unsaved work', () => {
  const loading = w.document.createElement('aurelvi-studio');
  w.document.body.append(loading);
  try {
    assert.equal(loading.shadowRoot.querySelector('header .studio-return').getAttribute('href'), '/');
    const link = studio.shadowRoot.querySelector('header .studio-return');
    assert.equal(link.href, 'https://ha.test/');
    assert.match(link.textContent, /Späť do Home Assistanta/);
    const confirm = w.confirm;
    let prompt;
    studio.dirty = true;
    w.confirm = (message) => { prompt = message; return false; };
    try {
      const click = new w.MouseEvent('click', { bubbles: true, cancelable: true });
      link.dispatchEvent(click);
      assert(click.defaultPrevented);
      assert.equal(prompt, 'Opustiť neuložené zmeny?');
    } finally {
      studio.dirty = false;
      w.confirm = confirm;
    }
  } finally {
    loading.remove();
  }
});
await test('Entity selectors contain HA entities without HTML injection',()=>{assert(studio.shadowRoot.querySelector('option[value="fan.ceiling"]'));store.panels[0].name='<img src=x>';studio.data=structuredClone(store);studio.render();assert(studio.shadowRoot.textContent.includes('<img src=x>'));assert(!studio.shadowRoot.querySelector('img[src="x"]'));});
await test('Changing speed count redraws 3 configurable speeds',()=>{change('Počet rýchlostí','3');assert.equal(studio.draft.pages[0].fan.speeds.length,3);assert(studio.dirty);});
await test('Draft undo preserves previous six speeds',()=>{let undo=studio.undo.pop();studio.draft=undo.config;studio.device=undo.device;studio.render();assert.equal(studio.draft.pages[0].fan.speeds.length,6);});
await test('Custom action form preserves service while editing target',()=>{studio.draft.pages[0].fan.extras=[{id:'custom',label:'Režim',icon:'sparkles',actions:[{service:'script.turn_on',target:{entity_id:'script.old'}}]}];studio.render();change('Akcia Home Assistanta','scene.turn_on');change('Cieľová entita','scene.evening');assert.equal(studio.draft.pages[0].fan.extras[0].actions[0].service,'scene.turn_on');assert.equal(studio.draft.pages[0].fan.extras[0].actions[0].target.entity_id,'scene.evening');});
await test('Hide controls and change fan entity are real draft edits',()=>{change('Teplota svetla',false);assert.equal(studio.draft.pages[0].fan.controls.temperature,false);change('Ventilátor','fan.other');assert.equal(studio.draft.pages[0].fan.fanEntity,'fan.other');});
await test('Save transmits revision and settings to integration',async()=>{await studio.save();let call=calls.findLast(c=>c.action==='save');assert.equal(call.data.revision,0);assert.equal(call.data.config.pages[0].fan.fanEntity,'fan.other');assert.equal(studio.dirty,false);});
await test('Display settings include theme, saver, schedule and default page',()=>{studio.tab='display';studio.render();change('Dizajn','night');assert.equal(studio.draft.theme,'night');change('Automatický nočný vzhľad',true);assert.equal(studio.device.nightMode.enabled,true);});
await test('Admin manages GitHub, backup, restore and diagnostics',()=>{studio.tab='manage';studio.render();let text=studio.shadowRoot.textContent;for(let label of ['Exportovať konfiguráciu','Importovať konfiguráciu','Obnoviť predchádzajúcu konfiguráciu','Aktualizácie z GitHubu','Diagnostika'])assert(text.includes(label));});
await test('Health card shows entity errors and recovery controls',()=>{studio.data.panels[0].health={ok:false,issues:[{message:'Chýba entita',hint:'Vyber entitu',entities:['fan.missing'],level:'warning'}]};studio.render();for(let text of ['Kontrola pripojenia','fan.missing','Znovu odoslať konfiguráciu','Stiahnuť diagnostiku'])assert(studio.shadowRoot.textContent.includes(text));});
await test('Backend message keys with JSON params are translated, other text is shown unchanged',()=>{studio.data.panels[0].health={ok:false,issues:[{message:'studio.manage.release|{"version":"1.2","asset":"a.apk"}',hint:'Plain hint',level:'warning'}]};studio.tab='manage';studio.render();const text=studio.shadowRoot.textContent;assert(text.includes('Vydanie 1.2 · a.apk'));assert(text.includes('Plain hint'));});
await test('Background polling preserves unfinished management fields',async()=>{change('Názov panela','New room');const input=field('Názov panela');await studio.refreshStatus();assert.equal(field('Názov panela'),input);assert.equal(input.value,'New room');});
await test('Rename sends only name and panel ID',async()=>{[...studio.shadowRoot.querySelectorAll('button')].find(b=>b.textContent==='Premenovať panel').click();await new Promise(r=>setTimeout(r,0));const call=calls.findLast(c=>c.action==='rename');assert.equal(call.panel_id,'test');assert.deepEqual(JSON.parse(JSON.stringify(call.data)),{name:'New room'});});
await test('Offline save reports waiting rather than delivered configuration',async()=>{store.panels[0].health={mqttConnected:false,panelOnline:false,issues:[]};await studio.save();assert(studio.message.includes('po obnovení pripojenia'));});
await test('Grid supports draggable cells and custom action JSON',()=>{studio.draft.pages=[{id:'grid',type:'grid',title:'Domov',grid:{columns:2,rows:2},tiles:[{id:'light',type:'button',behavior:'toggle',entity:'light.ceiling',label:'Svetlo',row:1,col:1}]}];studio.tab='pages';studio.render();assert.equal(studio.shadowRoot.querySelectorAll('.grid-cell').length,4);assert(studio.shadowRoot.querySelector('.grid-cell.occupied').draggable);assert(field('Vlastné akcie podľa udalosti'));});
await test('Camera and weather forms use entity lists',()=>{studio.draft.pages=[{id:'cam',type:'camera',camera:{cameras:[{entity:'camera.front'}]}}];studio.render();assert(field('Kamera'));studio.draft.pages=[{id:'weather',type:'weather'}];studio.render();assert(field('Weather entita'));});
await test('German locale, Slovak locale and 80 skin choices preserve drafts',async()=>{studio.tab='display';if(fs.existsSync(__dirname+'/../locale/de.json')){studio.hass={...hass,language:'de'};await studio.i18nReady;assert(studio.shadowRoot.textContent.includes("Erscheinungsbild und Bildschirmschoner"));assert(field("Design").querySelectorAll('option').length===80);}else{console.log('SKIP German Studio text: locale/de.json not restored; checking English instead');studio.hass={...hass,language:'en'};await studio.i18nReady;assert(studio.shadowRoot.textContent.includes('Appearance and screensaver'));assert(field('Panel skin').querySelectorAll('option').length===80);}const draft=JSON.stringify(studio.draft);studio.hass={...hass,language:'sk'};await studio.i18nReady;assert(studio.shadowRoot.textContent.includes('Vzhľad a šetrič'));assert.equal(JSON.stringify(studio.draft),draft);assert(field('Veľkosť ikon (px)'));});
await test('Notification tab preserves a full draft and renders copyable HA action',()=>{studio.tab='notify';studio.render();change('Nadpis','Door');change('Správa','Someone is here');assert(studio.shadowRoot.textContent.includes('Someone is here'));assert(studio.shadowRoot.textContent.includes('aurelvi.notify'));assert(studio.shadowRoot.textContent.includes('Kopírovať akciu'));assert.equal(studio.notificationDraft.title,'Door');});
await test('Advanced JSON edits change only the draft until Save',()=>{studio.tab='advanced';studio.render();const input=studio.shadowRoot.querySelector('textarea');const doc=JSON.parse(input.value);doc.device.iconSize=52;input.value=JSON.stringify(doc);const before=calls.filter(c=>c.action==='save').length;[...studio.shadowRoot.querySelectorAll('button')].find(b=>b.textContent==='Použiť do editora').click();assert.equal(studio.device.iconSize,52);assert.equal(calls.filter(c=>c.action==='save').length,before);});
await test('Room builder infers six fan speeds and links only a light on the same device',()=>{studio.tab='pages';hass.states['cover.blind']={state:'closed',attributes:{friendly_name:'Blind'}};hass.states['sensor.temp']={state:'21',attributes:{friendly_name:'Temperature'}};studio.hass=hass;const before=calls.filter(c=>c.action==='save').length;const pages=studio.buildRoomDraft({name:'Living room'},[{entity_id:'fan.ceiling',device_id:'fan-device'},{entity_id:'light.ceiling',device_id:'fan-device'},{entity_id:'cover.blind',device_id:'cover-device'},{entity_id:'sensor.temp'}]);const fan=pages.find(p=>p.type==='fan').fan;assert.equal(fan.speeds.length,6);assert.equal(fan.lightEntity,'light.ceiling');assert.equal(fan.controls.direction,true);const grid=pages.find(p=>p.type==='grid');assert(grid.tiles.some(t=>t.entity==='cover.blind'&&t.type==='rocker'));assert(grid.tiles.some(t=>t.entity==='sensor.temp'&&t.type==='readout'));assert.equal(calls.filter(c=>c.action==='save').length,before);assert(studio.dirty);});
await test('Main layout exposes room builder, theme gallery and wallpaper controls',()=>{studio.tab='pages';studio.render();assert(studio.shadowRoot.querySelector('.workspace .pages'));assert(studio.shadowRoot.querySelector('.workspace .preview-wrap'));assert(studio.shadowRoot.querySelector('.workspace .inspector'));assert(studio.shadowRoot.querySelector('.studio-hero').textContent.includes('Vytvoriť miestnosť'));assert.equal(studio.shadowRoot.querySelectorAll('.theme-swatch').length,80);assert.equal(studio.shadowRoot.querySelectorAll('.wallpaper-swatch').length,6);assert(studio.shadowRoot.querySelector('input[type=file]'));const forest=[...studio.shadowRoot.querySelectorAll('.wallpaper-swatch')].find(b=>b.textContent==='Les');forest.click();assert.equal(studio.device.wallpaper.id,'forest');assert(studio.dirty);});
await test("Templates remap entities and service targets and create a previewable draft", async () => {
  const page = { id: "settings", title: "Fan settings", type: "grid", grid: { rows: 1, columns: 1 }, tiles: [{
    id: "mode", type: "switcher", row: 1, col: 1, entity: "fan.ceiling",
    stateAttribute: "preset_mode", stateKey: "aurelvi_attr_fan_ceiling_preset_mode",
    bindings: { press: { service: "fan.set_preset_mode", target: { entity_id: ["fan.ceiling"] } } },
  }] };
  hass.states["fan.bedroom"] = { state: "on", attributes: {} };
  studio.hass = hass;
  store.templates = [{ id: "saved", name: "Fan settings", page }];
  await studio.refreshStatus();
  studio.tab = "pages";
  studio.render();
  const click = (label) => [...studio.shadowRoot.querySelectorAll("button")].find((button) => button.textContent === label).click();
  click("Šablóny stránok");
  change("fan.ceiling", "fan.bedroom");
  click(studio.shadowRoot.querySelector(".modal button.primary").textContent);
  const tile = studio.draft.pages.at(-1).tiles[0];
  assert.notEqual(tile.id, "mode");
  assert.equal(tile.entity, "fan.bedroom");
  assert.equal(tile.bindings.press.target.entity_id[0], "fan.bedroom");
  assert.equal(tile.stateKey, "aurelvi_attr_fan_bedroom_preset_mode");
  assert.equal(store.templates[0].page.tiles[0].entity, "fan.ceiling");
  assert(studio.shadowRoot.querySelector("iframe"));
});
await test("A thermostat draft imported without a fallback tile remains editable", () => {
  const thermostat = { id: "heat", type: "grid", grid: { rows: 1, columns: 1 }, tiles: [],
    thermostat: { entity: "climate.hall" } };
  studio.draft.pages.push(thermostat);
  studio.pageIndex = studio.draft.pages.length - 1;
  studio.render();
  change("Entita kúrenia alebo klimatizácie", "climate.bedroom");
  assert.equal(thermostat.thermostat.entity, "climate.bedroom");
  assert.equal(studio.error, false);
});
await test("Studio selects the doorbell sensor, camera and revision of each target panel", async () => {
  store.panels[0].name = "Chodba";
  hass.states["binary_sensor.bell"] = { state: "off", attributes: {} };
  store.panels.push({ ...store.panels[0], id: "other", name: "Spálňa", revision: 6 });
  await studio.load();
  studio.tab = "manage";
  studio.render();
  change("Snímač zvončeka", "binary_sensor.bell");
  change("Kamera", "camera.entry");
  change("Spálňa", true);
  const card = [...studio.shadowRoot.querySelectorAll("section")].find((section) => section.querySelector("h2").textContent === "Zvonček");
  card.querySelector("button.primary").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const request = calls.findLast((call) => call.action === "doorbell_configure");
  assert.equal(request.data.doorbell.camera.entity, "camera.entry");
  assert.equal(request.data.revisions.other, 6);
  assert.equal(request.data.revisions.test, store.panels[0].revision);
});
studio.remove();w.close();console.log(count+' Studio checks passed');})().catch(e=>{console.error(e);studio.remove();w.close();process.exitCode=1;});
