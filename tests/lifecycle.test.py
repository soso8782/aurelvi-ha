"""Lifecycle/config-flow endpoints with isolated HA adapters and real module code."""
import asyncio,importlib.util,sys,types,unittest
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0,str(Path(__file__).parent))
import importlib
bridge=importlib.import_module('integration.test') if False else None
# Reuse the bridge adapter module without running its unittest main.
spec=importlib.util.spec_from_file_location('aurelvi_test_adapters',Path(__file__).with_name('integration.test.py'));ad=importlib.util.module_from_spec(spec);spec.loader.exec_module(ad)
def module(name):return ad.module(name)
frontend=module('homeassistant.components.frontend');panel=module('homeassistant.components.panel_custom');websocket=module('homeassistant.components.websocket_api');http=module('homeassistant.components.http');const=module('homeassistant.const');ce=module('homeassistant.config_entries')
const.Platform=Enum('Platform',{name.upper():name for name in ['sensor','binary_sensor','button','number','switch','media_player','update','notify']})
http.StaticPathConfig=lambda *args:args
exceptions=module('homeassistant.exceptions')
class HomeAssistantError(Exception):
    def __init__(self,*args,translation_domain=None,translation_key=None,translation_placeholders=None):
        super().__init__(*args);self.translation_domain=translation_domain;self.translation_key=translation_key;self.translation_placeholders=translation_placeholders
exceptions.HomeAssistantError=HomeAssistantError
for name in ['require_admin','async_response']:setattr(websocket,name,lambda fn:fn)
websocket.websocket_command=lambda schema:lambda fn:fn
websocket.async_register_command=lambda *args:None
frontend.async_remove_panel=lambda hass,path:hass.removed.append(path)
async def register(hass,**kwargs):hass.panel=kwargs
panel.async_register_panel=register
class FakeFlow:
 def __init_subclass__(cls,domain=None,**kwargs):cls.domain=domain
 def _async_current_entries(self):return self.existing
 def async_abort(self,reason):return {'type':'abort','reason':reason}
 def async_show_form(self,**kwargs):return {'type':'form',**kwargs}
 def async_create_entry(self,**kwargs):return {'type':'create_entry',**kwargs}
 async def async_set_unique_id(self,id):self.unique=id
 def _abort_if_unique_id_configured(self):pass
ce.ConfigFlow=FakeFlow
root=ad.PKG
spec=importlib.util.spec_from_file_location('aurelvi_live',root/'__init__.py',submodule_search_locations=[str(root)]);integration=importlib.util.module_from_spec(spec);sys.modules['aurelvi_live']=integration;spec.loader.exec_module(integration)
flow_spec=importlib.util.spec_from_file_location('aurelvi_live.config_flow',root/'config_flow.py');flow=importlib.util.module_from_spec(flow_spec);flow_spec.loader.exec_module(flow)
class Connection:
 def __init__(self):self.results=[];self.errors=[]
 def send_result(self,id,data):self.results.append((id,data))
 def send_error(self,*args):self.errors.append(args)
class Lifecycle(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.hass=ad.Hass();self.hass.data={};self.hass.removed=[];self.hass.panel=None;self.hass.services.async_register=lambda *args,**kwargs:None;self.hass.services.async_remove=lambda *args:None
  async def static(paths):self.hass.static=paths
  async def forward(*args):self.hass.forwarded=args
  async def unload(*args):return True
  self.hass.http=types.SimpleNamespace(async_register_static_paths=static);self.hass.config_entries=types.SimpleNamespace(async_forward_entry_setups=forward,async_unload_platforms=unload,async_entries=lambda domain:[{}]);self.entry=types.SimpleNamespace(entry_id='entry')
 async def test_setup_and_unload(self):
  self.assertTrue(await integration.async_setup(self.hass,{}));self.assertTrue(await integration.async_setup_entry(self.hass,self.entry));self.assertEqual(self.hass.panel['webcomponent_name'],'aurelvi-studio');self.assertTrue(self.hass.panel['require_admin']);self.assertTrue(await integration.async_unload_entry(self.hass,self.entry));self.assertIn('aurelvi',self.hass.removed)
 async def test_websocket_config_operations(self):
  await integration.async_setup(self.hass,{});await integration.async_setup_entry(self.hass,self.entry);c=Connection();await integration.ws_command(self.hass,c,{'id':1,'action':'add','panel_id':'room','data':{'name':'Room'}});self.assertTrue(c.results);await integration.ws_command(self.hass,c,{'id':2,'action':'save','panel_id':'room','data':{'config':{'pages':[ad.fan_page()]},'device':{},'revision':0}});self.assertEqual(c.results[-1][1]['revision'],1);await integration.async_unload_entry(self.hass,self.entry)
 async def test_reject_unknown_command(self):
  await integration.async_setup(self.hass,{});await integration.async_setup_entry(self.hass,self.entry);c=Connection();await integration.ws_command(self.hass,c,{'id':1,'action':'command','panel_id':'room','data':{'name':'arbitrary_install'}});self.assertEqual(c.errors[0][1],'invalid_request');await integration.async_unload_entry(self.hass,self.entry)
 async def test_studio_adb_update_uses_the_paired_endpoint_even_if_mqtt_is_offline(self):
  await integration.async_setup(self.hass, {})
  await integration.async_setup_entry(self.hass, self.entry)
  hub = self.entry.runtime_data
  hub.panels['room'] = {'paired': True, 'adb': {'host': '192.168.1.10', 'port': 5556}}
  hub.status['room'] = {'online': False}
  client = Connection()
  with patch('aurelvi_live.adb.async_command', new_callable=AsyncMock) as command:
   command.return_value = {'output': 'installed'}
   await integration.ws_command(self.hass, client, {'id': 1, 'action': 'install_adb_update',
      'panel_id': 'room', 'data': {'host': '192.168.1.99'}})
   command.assert_awaited_once_with(hub, {'operation': 'install', 'host': '192.168.1.10', 'port': 5556})
   self.assertEqual(client.results, [(1, {'output': 'installed'})])
   await integration.ws_command(self.hass, client, {'id': 2, 'action': 'install_adb_update',
      'panel_id': 'unknown', 'data': {}})
   self.assertEqual(client.errors[-1], (2, 'invalid_request', 'backend.adb.unknown_panel'))
  self.assertFalse(any(topic.endswith('/cmd/update') for topic, _, _ in self.hass.mqtt))
 async def test_official_update_entity_requires_an_administrator_for_adb(self):
  update = module('homeassistant.components.update')
  update.UpdateEntity = type('UpdateEntity', (), {})
  update.UpdateEntityFeature = types.SimpleNamespace(INSTALL=1, RELEASE_NOTES=2)
  entity = module('homeassistant.helpers.entity')
  entity.Entity = type('Entity', (), {})
  entity.DeviceInfo = dict
  sys.modules['homeassistant.helpers.dispatcher'].async_dispatcher_connect = lambda *args: None
  from aurelvi_live.update import PanelUpdate

  await integration.async_setup(self.hass, {})
  await integration.async_setup_entry(self.hass, self.entry)
  hub = self.entry.runtime_data
  hub.settings['githubRepo'] = 'Soso8782/Aurelvi-APK'
  hub.latest = {'url': 'https://github.com/soso8782/aurelvi-apk/releases/download/v0.3.17/Aurelvi-0.3.17.apk'}
  panel_update = PanelUpdate(hub, 'room')
  panel_update.hass = self.hass
  panel_update._context = types.SimpleNamespace(user_id='operator')
  self.hass.auth = types.SimpleNamespace(async_get_user=AsyncMock(return_value=types.SimpleNamespace(is_admin=False)))
  with patch('aurelvi_live.update.async_install_latest', new_callable=AsyncMock) as install:
   with self.assertRaises(HomeAssistantError) as failure:
    await panel_update.async_install()
   self.assertEqual(failure.exception.translation_key, 'adb_failed')
   install.assert_not_awaited()
   self.hass.auth.async_get_user.return_value.is_admin = True
   await panel_update.async_install()
   install.assert_awaited_once_with(hub, 'room')
 async def test_adb_install_progress_is_scoped_to_the_requested_install(self):
  await integration.async_setup(self.hass, {})
  await integration.async_setup_entry(self.hass, self.entry)
  hub = self.entry.runtime_data
  hub.adb_install_progress = {'id': 'active-install', 'phase': 'transfer', 'percent': 37}
  client = Connection()
  await integration.ws_command(self.hass, client, {'id': 1, 'action': 'adb_install_progress',
                                                  'data': {'progress_id': 'other-install'}})
  await integration.ws_command(self.hass, client, {'id': 2, 'action': 'adb_install_progress',
                                                  'data': {'progress_id': 'active-install'}})
  self.assertEqual(client.results, [(1, None), (2, hub.adb_install_progress)])
 async def test_flow_reuses_existing_mqtt(self):
  f=flow.AurelviConfigFlow();f.hass=self.hass;f.existing=[];self.assertEqual((await f.async_step_user())['type'],'form');self.assertEqual((await f.async_step_user({}))['type'],'create_entry');self.assertEqual(f.unique,'aurelvi')
 async def test_flow_mqtt_required(self):
  f=flow.AurelviConfigFlow();f.hass=self.hass;f.existing=[];self.hass.config_entries.async_entries=lambda domain:[];self.assertEqual((await f.async_step_user({}))['errors']['base'],'mqtt_missing')
 async def test_flow_single_hub(self):
  f=flow.AurelviConfigFlow();f.hass=self.hass;f.existing=[{}];self.assertEqual((await f.async_step_user())['reason'],'single_instance_allowed')
if __name__=='__main__':unittest.main(verbosity=2)
