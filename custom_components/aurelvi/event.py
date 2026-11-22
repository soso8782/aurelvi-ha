"""Panel happenings as event entities: alarm clock, button presses and notification answers."""
from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import SIGNAL_EVENT
from .entity import AurelviEntity,add_dynamic

class PanelEvent(AurelviEntity,EventEntity):
    def __init__(self,h,p,key,kind,types):
        super().__init__(h,p,key,key);self.kind=kind;self._attr_event_types=types
    @callback
    def _fired(self,pid,kind,data):
        if pid!=self.pid or kind!=self.kind:return
        if kind=='alarm':event_type='alarm_fired'
        elif kind=='press':event_type='press'
        else:event_type=data.get('status')
        if event_type not in self._attr_event_types:return
        self._trigger_event(event_type,{k:v for k,v in data.items() if k!='panel_id'});self.async_write_ha_state()
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass,SIGNAL_EVENT,self._fired))

async def async_setup_entry(hass,entry,async_add_entities):
    await add_dynamic(hass,entry,async_add_entities,lambda h,p:[
        PanelEvent(h,p,'alarm','alarm',['alarm_fired']),
        PanelEvent(h,p,'button_press','press',['press']),
        PanelEvent(h,p,'notification_answer','notification',['shown','action','dismissed','expired'])])
