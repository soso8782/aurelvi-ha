"""Alarm clock time of the panel; its on/off switch lives in switch.py."""
from datetime import time as dtime
from homeassistant.components.time import TimeEntity
from .entity import AurelviEntity,add_dynamic

def alarm(entity):return entity.status.get('alarm',{}) or {}

class PanelAlarmTime(AurelviEntity,TimeEntity):
    def __init__(self,h,p):super().__init__(h,p,'alarm_time','Alarm time')
    @property
    def native_value(self):
        a=alarm(self)
        if type(a.get('hour')) is not int or type(a.get('minute')) is not int:return None
        return dtime(a['hour'],a['minute'])
    async def async_set_value(self,value):
        await self.hub.set_alarm(self.pid,alarm(self).get('enabled',True),value.hour,value.minute)

async def async_setup_entry(hass,entry,async_add_entities):
    await add_dynamic(hass,entry,async_add_entities,lambda h,p:[PanelAlarmTime(h,p)])
