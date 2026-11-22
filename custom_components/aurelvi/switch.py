from homeassistant.components.switch import SwitchEntity
from .entity import AurelviEntity,add_dynamic
from .i18n import msg
class PanelScreen(AurelviEntity,SwitchEntity):
    def __init__(self,h,p):super().__init__(h,p,'screen','Obrazovka')
    @property
    def is_on(self):return self.status.get('awake',{}).get('awake',True)
    async def async_turn_on(self,**kwargs):await self.hub.command(self.pid,'wake')
    async def async_turn_off(self,**kwargs):await self.hub.command(self.pid,'screen',{'action':'off'})
class PanelAlarmClock(AurelviEntity,SwitchEntity):
    """Enables the panel's alarm clock at the time held by the alarm time entity."""
    def __init__(self,h,p):super().__init__(h,p,'alarm_enabled','Alarm clock')
    @property
    def is_on(self):return bool(self.status.get('alarm',{}).get('enabled'))
    async def _set(self,enabled):
        a=self.status.get('alarm',{}) or {}
        if type(a.get('hour')) is not int or type(a.get('minute')) is not int:
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(msg('backend.hub.alarm_time_missing'))
        await self.hub.set_alarm(self.pid,enabled,a['hour'],a['minute'])
    async def async_turn_on(self,**kwargs):await self._set(True)
    async def async_turn_off(self,**kwargs):await self._set(False)
async def async_setup_entry(hass,entry,async_add_entities):await add_dynamic(hass,entry,async_add_entities,lambda h,p:[PanelScreen(h,p),PanelAlarmClock(h,p)])
