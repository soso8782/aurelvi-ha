// Capture website/assets/studio.png from the actual Studio editor with a mocked Home Assistant.
// Added during the repository recovery: the original screenshot was lost (see RECOVERY.md).
import {chromium} from 'playwright';
import fs from 'node:fs/promises';import http from 'node:http';import path from 'node:path';
const frontend=path.resolve('custom_components/aurelvi/frontend');
const page$=`<!doctype html><html lang="en"><head><meta charset="utf-8"><style>html,body{margin:0;background:#f4f1ea;font-family:Roboto,system-ui,sans-serif}aurelvi-studio{display:block;min-height:100vh}</style></head><body><script src="/aurelvi-static/studio.js"></script></body></html>`;
const server=http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost');if(url.pathname==='/'){res.setHeader('Content-Type','text/html');return res.end(page$);}
 if(!url.pathname.startsWith('/aurelvi-static/'))throw Error();const target=path.resolve(frontend,'.'+url.pathname.slice('/aurelvi-static'.length));if(!target.startsWith(frontend+path.sep))throw Error();
 const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.webp':'image/webp','.svg':'image/svg+xml','.json':'application/json'};res.setHeader('Content-Type',types[path.extname(target)]||'application/octet-stream');res.end(await fs.readFile(target));}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(8777,'127.0.0.1',r));let browser;
try{
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1800,height:800}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8777/');await page.waitForFunction(()=>customElements.get('aurelvi-studio'));
 await page.evaluate(()=>{
  const speeds=[17,33,50,67,83,100].map((percentage,i)=>({label:String(i+1),percentage}));
  const pages=[
   {id:'fan',type:'fan',title:'Living room fan',fan:{fanEntity:'fan.ceiling',lightEntity:'light.ceiling',speeds,controls:{direction:true,brightness:true,temperature:true,allOff:true,timer:true},extras:[]}},
   {id:'clock',type:'clock',title:'Clock'},{id:'weather',type:'weather',title:'Weather'},{id:'music',type:'music',title:'Music'}];
  const store={version:'0.3.15',panels:[{id:'living',name:'Living room',paired:true,config:{theme:'empire-emerald',pages},device:{theme:'empire-emerald',uiLanguage:'en'},revision:3,history:[],status:{online:true,info:{version:'Aurelvi 0.3.15'},sys:{}}}],timers:{},settings:{},latest:{},logs:[]};
  const hass={language:'en',themes:{darkMode:false},states:{'fan.ceiling':{entity_id:'fan.ceiling',state:'on',attributes:{friendly_name:'Ceiling fan',percentage:50,direction:'forward'}},'light.ceiling':{entity_id:'light.ceiling',state:'on',attributes:{friendly_name:'Ceiling light',brightness:180,color_temp_kelvin:3000}},'weather.home':{entity_id:'weather.home',state:'sunny',attributes:{friendly_name:'Home',temperature:22}}},
   callWS:async msg=>msg.action==='list'?structuredClone(store):true};
  const studio=document.createElement('aurelvi-studio');studio.hass=hass;document.body.append(studio);window.__studio=studio;
 });
 await page.waitForTimeout(2500);
 await page.evaluate(async()=>{const s=window.__studio;if(s.i18nReady)await s.i18nReady;await document.fonts.ready;});
 await page.waitForTimeout(1500);
 await page.screenshot({path:'website/assets/studio.png'});
 if(errors.length)console.warn('Studio page errors:',errors.join(' | '));
 console.log('Captured website/assets/studio.png from the actual Studio editor');
}finally{if(browser)await browser.close();server.close();}
