"""Real Aurelvi bridge exercised with isolated Home Assistant service/MQTT adapters."""
import asyncio,copy,importlib.util,json,sys,types,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'custom_components/aurelvi'
# Minimal HA adapters; actual bridge/validation files are imported unchanged.
def module(name):
 m=types.ModuleType(name);m.__path__=[];sys.modules[name]=m;return m
for name in ['homeassistant','homeassistant.components','homeassistant.core','homeassistant.helpers','homeassistant.helpers.device_registry','homeassistant.helpers.aiohttp_client','homeassistant.helpers.dispatcher','homeassistant.helpers.event','homeassistant.helpers.network','homeassistant.helpers.storage','homeassistant.components.mqtt']:module(name)
core=sys.modules['homeassistant.core'];core.callback=lambda fn:fn;core.Context=object
mqtt=sys.modules['homeassistant.components.mqtt']
async def publish(hass,topic,payload,**kwargs):hass.mqtt.append((topic,json.loads(payload) if payload.startswith(('{','[')) else payload,kwargs))
async def subscribe(hass,topic,fn,qos):hass.subscriptions.append((topic,fn));return lambda:None
mqtt.is_connected=lambda hass:True
mqtt.async_publish=publish;mqtt.async_subscribe=subscribe
sys.modules['homeassistant.helpers.device_registry'].async_get=lambda hass:types.SimpleNamespace(async_get_or_create=lambda **kw:hass.devices.append(kw))
sys.modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession=lambda hass:None
sys.modules['homeassistant.helpers.dispatcher'].async_dispatcher_send=lambda *a:None
sys.modules['homeassistant.helpers.network'].get_url=lambda *a,**k:'http://ha.test:8123'
sys.modules['homeassistant.helpers.event'].async_track_time_interval=lambda *a:lambda:None
jobs=[]
def later(hass,delay,fn):
 record={'delay':delay,'callback':fn,'cancelled':False};jobs.append(record)
 return lambda:record.update(cancelled=True)
sys.modules['homeassistant.helpers.event'].async_call_later=later
class Store:
 def __init__(self,*a):self.saved={}
 async def async_load(self):return copy.deepcopy(self.saved)
 async def async_save(self,data):self.saved=copy.deepcopy(data)
 def async_delay_save(self,fn,delay=0):self.delayed=delay;self.saved=copy.deepcopy(fn())
sys.modules['homeassistant.helpers.storage'].Store=Store
package=module('aurelvi_test');package.__path__=[str(PKG)]
from aurelvi_test.models import validate_config,fan_page,mirror,validate_device,entities
from aurelvi_test.hub import Hub
class State:
 def __init__(self,entity_id,state='on',**attributes):self.entity_id=entity_id;self.state=state;self.attributes=attributes
class Hass:
 async def async_add_executor_job(self,fn,*args):return fn(*args)
 def __init__(self):
  self.mqtt=[];self.calls=[];self.subscriptions=[];self.devices=[];self.values={};self.fail=False
  self.states=types.SimpleNamespace(get=self.values.get)
  self.bus=types.SimpleNamespace(async_listen=lambda *a:lambda:None,async_fire=lambda *a:None)
  self.services=types.SimpleNamespace(async_call=self.call)
 async def call(self,domain,service,data,**kwargs):
  if self.fail:raise ValueError('service failed')
  self.calls.append((domain,service,data,kwargs))
  if domain=='weather':return {'weather.home':{'forecast':[{'datetime':'2026-10-14','temperature':23}]}}
 def async_create_task(self,coro):return asyncio.create_task(coro)
class Validation(unittest.TestCase):
 def test_six_speed_template(self):validate_config({'pages':[fan_page()]})
 def test_custom_preset_and_action(self):
  p=fan_page();p['fan']['speeds']=[{'preset_mode':'quiet'},{'actions':[{'service':'script.turn_on','target':{'entity_id':'script.breeze'}}]}];validate_config({'pages':[p]})
 def test_reject_invalid_speed(self):
  p=fan_page();p['fan']['speeds'][0]['percentage']=101
  with self.assertRaises(ValueError):validate_config({'pages':[p]})
 def test_reject_duplicate_pages(self):
  with self.assertRaises(ValueError):validate_config({'pages':[fan_page(),fan_page()]})
 def test_reject_overlapping_grid(self):
  with self.assertRaises(ValueError):validate_config({'pages':[{'id':'grid','type':'grid','grid':{'columns':1,'rows':1},'tiles':[{'id':'a','type':'button','row':1,'col':1},{'id':'b','type':'button','row':1,'col':1}]}]})
 def test_light_and_fan_attributes(self):
  self.assertEqual(mirror(State('light.test',brightness=128))['brightness'],.502)
  self.assertEqual(mirror(State('fan.test',percentage=50,direction='reverse'))['percentage'],50)
 def test_unavailable_has_no_green(self):self.assertEqual(mirror(State('fan.test','unavailable'))['on'],False)
 def test_device_bounds(self):
  with self.assertRaises(ValueError):validate_device({'screensaver':{'after':-1}},2)
 def test_custom_actions_index_entities(self):
  p=fan_page();p['fan']['extras']=[{'id':'scene','actions':[{'service':'scene.turn_on','target':{'entity_id':'scene.reading'}}]}]
  self.assertIn('scene.reading',entities({'pages':[p]}))
class Integration(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.hass=Hass();self.hub=Hub(self.hass,types.SimpleNamespace(entry_id='entry'));self.hub.panels={'test':{'name':'Room','paired':True,'config':{'v':1,'theme':'cream','pages':[fan_page('fan.ceiling','light.ceiling')]},'device':{},'revision':0,'history':[]}};self.hub.status={'test':{'online':True,'info':{},'sys':{}}}
  self.hass.values['fan.ceiling']=State('fan.ceiling',percentage=50,direction='forward');self.hass.values['light.ceiling']=State('light.ceiling',brightness=128,color_temp_kelvin=3000,min_color_temp_kelvin=2200,max_color_temp_kelvin=6500)
 async def event(self,button,value=None,event_id='e1',retain=False):
  await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/test/event',payload=json.dumps({'page':'fan','button':button,'action':'press','value':value,'eventId':event_id}),retain=retain))
 def call_data(self):return self.hass.calls[-1][:3]
 async def test_clock_language_follows_home_assistant_unless_chosen(self):
  self.hass.config=types.SimpleNamespace(language='sk')
  await self.hub.push('test');device=[d for t,d,_ in self.hass.mqtt if t=='aurelvi/panel/test/config/device'][-1]
  self.assertEqual(device['clockLanguage'],'sk-SK');self.assertNotIn('clockLanguage',self.hub.panels['test']['device'])
  self.hub.panels['test']['device']['clockLanguage']='de-DE';await self.hub.push('test')
  self.assertEqual([d for t,d,_ in self.hass.mqtt if t=='aurelvi/panel/test/config/device'][-1]['clockLanguage'],'de-DE')
  self.hass.config=types.SimpleNamespace(language='pl');self.hub.panels['test']['device'].pop('clockLanguage');await self.hub.push('test')
  self.assertEqual([d for t,d,_ in self.hass.mqtt if t=='aurelvi/panel/test/config/device'][-1]['clockLanguage'],'en-GB')
 async def test_alarm_fired_is_reported_whatever_page_is_shown(self):
  fired=[];sent=[];self.hass.bus.async_fire=lambda *a:fired.append(a)
  sys.modules['aurelvi_test.hub'].async_dispatcher_send=lambda *a:sent.append(a[1:])
  await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/test/event',payload=json.dumps({'page':'fan','button':'alarm','action':'alarm_fired','eventId':'a1'}),retain=False))
  self.assertEqual(fired,[('aurelvi_alarm_fired',{'panel_id':'test'})]);self.assertIn(('aurelvi_event','test','alarm',{}),sent)
  self.assertEqual(self.hass.mqtt[-1][1],{'eventId':'a1','button':'alarm','ok':True});self.assertEqual(self.hass.calls,[])
 async def test_button_press_is_forwarded_to_event_entities(self):
  sent=[];sys.modules['aurelvi_test.hub'].async_dispatcher_send=lambda *a:sent.append(a[1:])
  await self.event('fan.off')
  self.assertIn(('aurelvi_event','test','press',{'button':'fan.off','page':'fan','action':'press'}),sent);self.assertEqual(self.call_data()[:2],('fan','turn_off'))
 async def test_ping_measures_round_trip(self):
  task=asyncio.create_task(self.hub.ping('test',timeout=2));await asyncio.sleep(0)
  topic,doc,_=self.hass.mqtt[-1];self.assertEqual(topic,'aurelvi/panel/test/cmd/ping')
  await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/other/sys/pong',payload=json.dumps({'id':doc['id']}),retain=False))
  self.assertFalse(task.done())
  await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/test/sys/pong',payload=json.dumps({'id':doc['id'],'ts':1}),retain=False))
  result=await task;self.assertEqual(result['panel_id'],'test');self.assertGreaterEqual(result['rtt_ms'],0);self.assertEqual(self.hub.probes,{})
 async def test_ping_times_out(self):
  with self.assertRaises(ValueError):await self.hub.ping('test',timeout=0.01)
  self.assertEqual(self.hub.probes,{})
 async def test_discovery_collects_paired_and_unknown_panels(self):
  task=asyncio.create_task(self.hub.discover(timeout=0.05));await asyncio.sleep(0)
  topic,doc,_=self.hass.mqtt[-1];self.assertEqual(topic,'aurelvi/panel/discover')
  for pid in ['test','newpanel']:
   await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/'+pid+'/sys/discovery',payload=json.dumps({'id':doc['id'],'version':'0.3.17','ip':'10.0.0.2','secret':{'x':1}}),retain=False))
  result=await task
  self.assertEqual([(p['panel_id'],p['paired']) for p in result['panels']],[('newpanel',False),('test',True)])
  self.assertNotIn('secret',result['panels'][0]);self.assertNotIn('newpanel',self.hub.panels)
 async def test_notification_words_and_timeout_alias(self):
  await self.hub.notify('test',{'message':'Gate?','actions':['Yes','No'],'timeout':0})
  doc=self.hass.mqtt[-1][1];self.assertEqual(doc['actions'],[{'id':'Yes','label':'Yes'},{'id':'No','label':'No'}]);self.assertEqual(doc['timeoutS'],0);self.assertNotIn('timeout',doc)
  with self.assertRaises(ValueError):await self.hub.notify('test',{'message':'x','actions':[{'label':'no id'}]})
 async def test_set_alarm_validates_time(self):
  await self.hub.set_alarm('test',True,6,30);self.assertEqual(self.hass.mqtt[-1][:2],('aurelvi/panel/test/cmd/set_alarm',{'enabled':True,'hour':6,'minute':30}))
  for hour,minute in [(24,0),(6,60),('6',0)]:
   with self.assertRaises(ValueError):await self.hub.set_alarm('test',True,hour,minute)
 async def test_unrelated_state_change_is_ignored_without_walking_config(self):
  from unittest.mock import patch
  self.hub.refresh_entities();created=[]
  self.hass.async_create_task=lambda coro:(created.append(1),coro.close())
  with patch('aurelvi_test.hub.entities',side_effect=AssertionError('entities() called')):
   self.hub.state_changed(types.SimpleNamespace(data={'entity_id':'sensor.unrelated'}));self.assertEqual(created,[])
   self.hub.state_changed(types.SimpleNamespace(data={'entity_id':'fan.ceiling'}));self.assertEqual(created,[1])
 async def test_panel_scoped_signal_and_delayed_persist(self):
  sent=[];sys.modules['aurelvi_test.hub'].async_dispatcher_send=lambda *a:sent.append(a[1:])
  self.hub.changed('test');self.hub.changed();self.assertEqual(sent,[('aurelvi_changed','test'),('aurelvi_changed',None)])
  self.hub.schedule_persist();self.assertEqual(self.hub.store.delayed,2)
 async def test_startup_and_updates_with_nullable_light_attributes(self):
  self.hass.values['light.ceiling']=State('light.ceiling','off',brightness=None,color_temp_kelvin=None,color_temp=None)
  self.hub.store.saved={'panels':copy.deepcopy(self.hub.panels)}
  await self.hub.start()
  light=[doc for topic,doc,options in self.hass.mqtt if topic.endswith('/state/light_ceiling')]
  self.assertTrue(light);self.assertNotIn('brightness',light[-1]);self.assertFalse(light[-1]['on'])
  self.hass.values['light.ceiling']=State('light.ceiling','on',brightness=128,color_temp_kelvin=3000)
  await self.hub.publish_state('test','light.ceiling')
  self.assertEqual(self.hass.mqtt[-1][1]['brightness'],.502)
  self.hass.values['light.ceiling']=State('light.ceiling','unavailable',brightness=None)
  await self.hub.publish_state('test','light.ceiling')
  self.assertFalse(self.hass.mqtt[-1][1]['available'])
  await self.hub.close()
 async def test_speed6(self):
  await self.event('fan.speed.6');self.assertEqual(self.call_data(),('fan','set_percentage',{'percentage':100,'entity_id':'fan.ceiling'}));self.assertTrue(self.hass.mqtt[-1][1]['ok'])
 async def test_direction_reads_real_state(self):
  await self.event('fan.direction');self.assertEqual(self.call_data()[2]['direction'],'reverse')
 async def test_brightness(self):
  await self.event('fan.brightness',.42);self.assertEqual(self.call_data()[2]['brightness_pct'],42)
 async def test_kelvin_bounds(self):
  await self.event('fan.temperature',7000);self.assertFalse(self.hass.mqtt[-1][1]['ok']);self.assertEqual(self.hass.calls,[])
 async def test_all_off(self):
  await self.event('fan.all_off');self.assertEqual(len(self.hass.calls),2);self.assertEqual(self.call_data()[0],'light')
 async def test_unknown_button_no_service(self):
  await self.event('fan.secret');self.assertEqual(self.hass.calls,[]);self.assertFalse(self.hass.mqtt[-1][1]['ok'])
 async def test_retained_command_ignored(self):
  await self.event('fan.speed.6',retain=True);self.assertEqual(self.hass.calls,[])
 async def test_qos_duplicate_not_executed_twice(self):
  await self.event('fan.speed.6');await self.event('fan.speed.6');self.assertEqual(len(self.hass.calls),1)
 async def test_pending_discovery_cannot_control(self):
  self.hub.panels['test']['paired']=False;await self.event('fan.speed.6');self.assertEqual(self.hass.calls,[])
 async def test_offline_cannot_control(self):
  self.hub.status['test']['online']=False;await self.event('fan.speed.6');self.assertEqual(self.hass.calls,[])
 async def test_service_failure_negative_ack(self):
  self.hass.fail=True;await self.event('fan.speed.6');self.assertFalse(self.hass.mqtt[-1][1]['ok'])
 async def test_negative_ack_has_readable_text_for_old_apk_and_key_for_new(self):
  self.hub.panels['test']['device']={'uiLanguage':'sk'}
  await self.event('fan.unknown');ack=self.hass.mqtt[-1][1]
  self.assertFalse(ack['ok']);self.assertTrue(ack['messageKey'].startswith('backend.'))
  self.assertFalse(ack['message'].startswith('backend.'),ack['message']);self.assertTrue(ack['message'])
  self.hub.panels['test']['device']={'clockLanguage':'de-DE'};await self.event('fan.unknown',event_id='e2')
  self.assertFalse(self.hass.mqtt[-1][1]['message'].startswith('backend.'))
 async def test_timer_persists_and_executes(self):
  await self.event('fan.timer',120);self.assertIn('test',self.hub.store.saved['timers']);job=jobs[-1];self.assertAlmostEqual(job['delay'],7200,delta=1);await job['callback'](None);self.assertEqual(self.call_data()[:2],('fan','turn_off'));self.assertNotIn('test',self.hub.timers)
 async def test_timer_cancelled_and_restored_after_restart(self):
  await self.hub.set_timer('test','fan.ceiling',60);old=jobs[-1];saved=self.hub.store.saved
  h=Hub(self.hass,types.SimpleNamespace(entry_id='entry'));h.store.saved=saved;await h.start();self.assertIn('test',h.timers);self.assertLessEqual(jobs[-1]['delay'],60);await h.cancel_timer('test');self.assertTrue(jobs[-1]['cancelled']);await h.close()
 async def test_revision_conflict_no_overwrite(self):
  with self.assertRaises(ValueError):await self.hub.save('test',self.hub.panels['test']['config'],{},9)
  self.assertEqual(self.hub.panels['test']['revision'],0)
 async def test_history_restore(self):
  config=copy.deepcopy(self.hub.panels['test']['config']);config['theme']='night';await self.hub.save('test',config,{},0);await self.hub.restore('test',1);self.assertEqual(self.hub.panels['test']['config']['theme'],'cream');self.assertEqual(self.hub.panels['test']['revision'],2)
 async def test_camera_uses_local_signed_url(self):
  self.hass.values['camera.front']=State('camera.front',access_token='temporary-token');await self.hub.publish_state('test','camera.front');self.assertEqual(self.hass.mqtt[-1][1]['stream'],'http://ha.test:8123/api/camera_proxy_stream/camera.front?token=temporary-token')
 async def test_weather_first_request_after_host_start(self):
  from unittest.mock import patch
  self.hass.values['weather.home']=State('weather.home','sunny',temperature=21)
  with patch('aurelvi_test.hub.time.monotonic',return_value=30):
   await self.hub.weather('test',{'weather':{'entity':'weather.home'}})
   self.assertEqual(len(self.hass.mqtt),1)
   await self.hub.weather('test',{'weather':{'entity':'weather.home'}})
   self.assertEqual(len(self.hass.mqtt),1)
 async def test_weather_forecast(self):
  self.hass.values['weather.home']=State('weather.home','sunny',temperature=21,temperature_unit='°C');await self.hub.weather('test',{'type':'weather','weather':{'entity':'weather.home'}});self.assertEqual(self.hass.mqtt[-1][1]['forecast'][0]['temperature'],23)
 async def test_custom_scene_action(self):
  self.hub.panels['test']['config']['pages'][0]['fan']['extras']=[{'id':'reading','actions':[{'service':'scene.turn_on','target':{'entity_id':'scene.reading'}}]}];await self.event('fan.extra.reading');self.assertEqual(self.call_data()[:2],('scene','turn_on'))
 async def test_notification_action_is_integration_owned(self):
  await self.hub.notify('test',{'id':'notify1','actions':[{'id':'open','on_press':{'service':'cover.open_cover','target':{'entity_id':'cover.gate'}}}]});self.assertNotIn('on_press',self.hass.mqtt[-1][1]['actions'][0]);await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/test/sys/notification',payload=json.dumps({'id':'notify1','actionId':'open','status':'action'}),retain=False));self.assertEqual(self.call_data()[:2],('cover','open_cover'))
 async def test_grid_scoped_binding(self):
  self.hub.panels['test']['config']={'pages':[{'id':'grid','type':'grid','tiles':[{'id':'light','entity':'light.ceiling','type':'button','behavior':'toggle'}]}]};await self.hub.handle_event('test',{'page':'grid','button':'light','action':'toggle','eventId':'grid1'});self.assertEqual(self.call_data()[:2],('homeassistant','toggle'))
class Releases(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.hass=Hass();self.hub=Hub(self.hass,types.SimpleNamespace(entry_id='entry'));self.hub.settings={'githubRepo':'Owner/project'}
  self.doc={'tag_name':'v0.3.1','assets':[{'name':'Aurelvi.apk','browser_download_url':'https://github.com/owner/project/releases/download/v0.3.1/Aurelvi.apk'}],'body':'Updates','html_url':'https://github.com/owner/project/releases/tag/v0.3.1'};self.code=200
  test=self
  class Response:
   @property
   def status(self):return test.code
   content_length=None
   async def __aenter__(self):return self
   async def __aexit__(self,*args):return False
   @property
   def content(self):return self
   async def read(self,size):return json.dumps(test.doc).encode()
  class Session:
   def get(self,*args,**kwargs):return Response()
  self.original=sys.modules['aurelvi_test.hub'].async_get_clientsession
  sys.modules['aurelvi_test.hub'].async_get_clientsession=lambda hass:Session()
 async def asyncTearDown(self):sys.modules['aurelvi_test.hub'].async_get_clientsession=self.original
 async def test_github_asset_case_and_version(self):
  await self.hub.check_releases();self.assertEqual(self.hub.latest['version'],'0.3.1');self.assertTrue(self.hub.latest['url'].endswith('Aurelvi.apk'))
 async def test_github_multiple_assets(self):
  self.doc['assets'].append(dict(self.doc['assets'][0],name='Aurelvi-debug.apk'));await self.hub.check_releases();self.assertFalse(self.hub.latest);self.assertTrue(self.hub.logs)
 async def test_github_wrong_host(self):
  self.doc['assets'][0]['browser_download_url']='https://evil.test/owner/project/releases/download/v0.3.1/Aurelvi.apk';await self.hub.check_releases();self.assertFalse(self.hub.latest)
 async def test_github_draft_and_unknown_tag(self):
  self.doc['draft']=True;await self.hub.check_releases();self.assertFalse(self.hub.latest);self.doc.pop('draft');self.doc['tag_name']='nightly';await self.hub.check_releases();self.assertFalse(self.hub.latest)
 async def test_github_missing_release(self):
  self.code=404;await self.hub.check_releases();self.assertFalse(self.hub.latest);self.assertIn('404',self.hub.logs[-1]['message'])
class FanSettings(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=Integration.asyncSetUp
 async def test_attribute_projection_keeps_false_and_clears_missing(self):
  tile={'id':'wind','type':'switcher','entity':'fan.ceiling','stateAttribute':'oscillating','stateKey':'aurelvi_attr_fan_ceiling_oscillating','row':1,'col':1}
  self.hub.panels['test']['config']['pages'].append({'id':'settings','type':'grid','grid':{'columns':1,'rows':1},'tiles':[tile]})
  validate_config(self.hub.panels['test']['config'])
  self.hass.values['fan.ceiling'].attributes['oscillating']=False
  await self.hub.publish_state('test','fan.ceiling')
  topic,doc,flags=self.hass.mqtt[-1];self.assertTrue(topic.endswith('/state/aurelvi_attr_fan_ceiling_oscillating'));self.assertIs(doc['value'],False);self.assertTrue(doc['available']);self.assertTrue(flags['retain'])
  del self.hass.values['fan.ceiling'].attributes['oscillating']
  await self.hub.publish_state('test','fan.ceiling');self.assertTrue(self.hass.mqtt[-1][1]['available']);self.assertEqual(self.hass.mqtt[-1][1]['value'],'unknown')
  self.hass.values['fan.ceiling'].state='unavailable';await self.hub.publish_state('test','fan.ceiling');self.assertFalse(self.hass.mqtt[-1][1]['available'])
 async def test_wind_and_oscillation_bindings(self):
  tile={'id':'wind','type':'switcher','entity':'fan.ceiling','bindings':{'state:natural':{'service':'fan.set_preset_mode','target':{'entity_id':'fan.ceiling'},'data':{'preset_mode':'natural'}},'state:false':{'service':'fan.oscillate','target':{'entity_id':'fan.ceiling'},'data':{'oscillating':False}}}}
  page={'tiles':[tile]}
  await self.hub.grid_event('test',page,{'button':'wind','action':'state','value':'natural'})
  self.assertEqual(self.hass.calls[-1][:3],('fan','set_preset_mode',{'entity_id':'fan.ceiling','preset_mode':'natural'}))
  await self.hub.grid_event('test',page,{'button':'wind','action':'state','value':False})
  self.assertIs(self.hass.calls[-1][2]['oscillating'],False)
 async def test_number_step_reads_current_state_and_limits(self):
  action={'service':'number.set_value','target':{'entity_id':'number.timer'},'dynamic':'number_step','delta':1}
  self.hass.values['number.timer']=State('number.timer','0.5',min=0,max=1,step=.5)
  await self.hub.execute(action);self.assertEqual(self.hass.calls[-1][2]['value'],1)
  self.hass.values['number.timer'].state='1';await self.hub.execute(action);self.assertEqual(self.hass.calls[-1][2]['value'],1)
  action['delta']=-1;await self.hub.execute(action);self.assertEqual(self.hass.calls[-1][2]['value'],.5)
  self.hass.values['number.timer'].state='unavailable'
  with self.assertRaises(ValueError):await self.hub.execute(action)
  self.hass.values['number.timer'].state='nan'
  with self.assertRaises(ValueError):await self.hub.execute(action)
 async def test_projection_rejects_arbitrary_topic(self):
  config={'pages':[{'id':'settings','type':'grid','grid':{'columns':1,'rows':1},'tiles':[{'id':'x','type':'switcher','entity':'fan.ceiling','stateAttribute':'preset_mode','stateKey':'arbitrary','row':1,'col':1}]}]}
  with self.assertRaises(ValueError):validate_config(config)
class PanelFeatures(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=Integration.asyncSetUp

 async def test_thermostat_targets_confirmed_entity_and_rejects_unknown_mode(self):
  page = {'id': 'heat', 'type': 'grid', 'grid': {'columns': 1, 'rows': 1}, 'tiles': [],
          'thermostat': {'entity': 'climate.room'}}
  self.hub.panels['test']['config']['pages'].append(page)
  thermostat = State('climate.room', 'heat', temperature=20, current_temperature=18,
                     min_temp=12, max_temp=22, target_temp_step=.5,
                     hvac_modes=['off', 'heat'], hvac_action='heating')
  self.hass.values[thermostat.entity_id] = thermostat
  self.assertEqual(mirror(thermostat)['hvac_action'], 'heating')

  async def send(action, value, event_id):
   payload = {'page': page['id'], 'button': 'heat.thermostat', 'action': action,
              'value': value, 'eventId': event_id}
   await self.hub.receive(types.SimpleNamespace(topic='aurelvi/panel/test/event',
                                               payload=json.dumps(payload), retain=False))

  await send('temperature', 1, 'temperature1')
  self.assertEqual(self.hass.calls[-1][:3], ('climate', 'set_temperature',
                                            {'entity_id': 'climate.room', 'temperature': 20.5}))
  thermostat.attributes['temperature'] = 21.9
  await send('temperature', 1, 'temperature2')
  self.assertEqual(self.hass.calls[-1][2]['temperature'], 22)
  await send('mode', 'off', 'mode1')
  self.assertEqual(self.hass.calls[-1][:3], ('climate', 'set_hvac_mode',
                                            {'entity_id': 'climate.room', 'hvac_mode': 'off'}))
  await send('mode', 'unsupported', 'mode2')
  self.assertEqual(len(self.hass.calls), 3)
  self.assertFalse(self.hass.mqtt[-1][1]['ok'])
  thermostat.attributes.update(target_temp_low=20, target_temp_high=20.2)
  await send('low', 1, 'low1')
  self.assertEqual(self.hass.calls[-1][2]['target_temp_low'], 20.2)
  await send('high', 1, 'high1')
  self.assertEqual(self.hass.calls[-1][2], {'entity_id': 'climate.room',
                                          'target_temp_low': 20, 'target_temp_high': 20.7})

 async def test_doorbell_only_rings_selected_panels_on_rising_edge(self):
  self.hub.panels['other'] = copy.deepcopy(self.hub.panels['test'])
  self.hub.status['other'] = {'online': True}
  camera = State('camera.entry', 'idle', access_token='camera-test-token')
  self.hass.values[camera.entity_id] = camera
  doorbell = {'entity': 'binary_sensor.bell', 'camera': {'entity': camera.entity_id}}
  with self.assertRaises(ValueError):
   await self.hub.configure_doorbell({'test': 0, 'other': 4}, doorbell)
  self.assertNotIn('doorbell', self.hub.panels['test']['config'])
  await self.hub.configure_doorbell({'test': 0}, doorbell)
  self.assertIn(camera.entity_id, self.hub.entities_of('test'))
  self.hass.mqtt.clear()
  tasks = []
  self.hass.async_create_task = lambda coro: tasks.append(asyncio.create_task(coro))
  def state_changed(old, new):
   self.hub.state_changed(types.SimpleNamespace(data={'entity_id': 'binary_sensor.bell',
       'old_state': State('binary_sensor.bell', old), 'new_state': State('binary_sensor.bell', new)}))
  state_changed('off', 'on')
  state_changed('on', 'on')
  await asyncio.gather(*tasks)
  commands = [(topic, data, flags) for topic, data, flags in self.hass.mqtt if '/cmd/' in topic]
  self.assertEqual(len(commands), 1)
  self.assertEqual(commands[0][0], 'aurelvi/panel/test/cmd/doorbell')
  self.assertEqual(commands[0][1], {'camera': 'camera.entry'})
  self.assertFalse(commands[0][2]['retain'])
  await self.hub.configure_doorbell({'test': 1}, None)
  self.assertNotIn(camera.entity_id, self.hub.entities_of('test'))
  await self.hub.configure_doorbell({'test': 2}, {**doorbell, 'entity': 'event.bell'})
  self.hass.mqtt.clear()
  tasks.clear()
  self.hub.state_changed(types.SimpleNamespace(data={'entity_id': 'event.bell',
      'old_state': State('event.bell', '2026-11-21T18:00:00+00:00'),
      'new_state': State('event.bell', '2026-11-21T18:00:01+00:00')}))
  await asyncio.gather(*tasks)
  self.assertEqual(sum(topic.endswith('/cmd/doorbell') for topic, _, _ in self.hass.mqtt), 1)

 async def test_templates_are_independent_of_the_original_page_and_survive_reload(self):
  page = self.hub.panels['test']['config']['pages'][0]
  await self.hub.save_template(' Fan controls ', page)
  page['title'] = 'Updated'
  snapshot = self.hub.snapshot()['templates'][0]
  self.assertEqual(snapshot['name'], 'Fan controls')
  self.assertNotEqual(snapshot['page']['title'], 'Updated')
  await self.hub.start()
  self.assertEqual(self.hub.snapshot()['templates'][0], snapshot)
  await self.hub.remove_template(snapshot['id'])
  self.assertEqual(self.hub.store.saved['templates'], {})

if __name__=='__main__':unittest.main(verbosity=2)
