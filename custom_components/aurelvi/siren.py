"""Panel loudspeaker as a siren using the bundled siren sound."""
from homeassistant.components.siren import SirenEntity,SirenEntityFeature
from .entity import AurelviEntity,add_dynamic

class PanelSiren(AurelviEntity,SirenEntity):
    _attr_supported_features=SirenEntityFeature.TURN_ON|SirenEntityFeature.TURN_OFF|SirenEntityFeature.TONES|SirenEntityFeature.VOLUME_SET
    _attr_available_tones=['siren','alarm','alarmo','alarm_beep','ding']
    def __init__(self,h,p):super().__init__(h,p,'siren','Siren')
    @property
    def is_on(self):
        media=self.status.get('media',{})
        return media.get('state')=='playing' and media.get('asset') in self._attr_available_tones
    async def async_turn_on(self,**kwargs):
        tone=kwargs.get('tone') or 'siren'
        if tone not in self._attr_available_tones:tone='siren'
        doc={'action':'play','asset':tone,'title':'Siren'}
        if kwargs.get('volume_level') is not None:doc['volume']=kwargs['volume_level']
        await self.hub.command(self.pid,'wake');await self.hub.command(self.pid,'media',doc)
    async def async_turn_off(self,**kwargs):await self.hub.command(self.pid,'media',{'action':'stop'})

async def async_setup_entry(hass,entry,async_add_entities):
    await add_dynamic(hass,entry,async_add_entities,lambda h,p:[PanelSiren(h,p)])
