"""Latest panel screenshot as a camera; aurelvi.screenshot asks the panel for a new one."""
import base64
from homeassistant.components.camera import Camera
from .entity import AurelviEntity,add_dynamic

class PanelScreenshot(AurelviEntity,Camera):
    _attr_is_streaming=False
    def __init__(self,h,p):
        AurelviEntity.__init__(self,h,p,'screenshot','Screenshot');Camera.__init__(self)
        self._attr_unique_id=p+'_screenshot'
    @property
    def available(self):return bool(self.hub.status.get(self.pid,{}).get('screenshot'))
    async def async_camera_image(self,width=None,height=None):
        data=self.hub.status.get(self.pid,{}).get('screenshot')
        return base64.b64decode(data) if data else None

async def async_setup_entry(hass,entry,async_add_entities):
    await add_dynamic(hass,entry,async_add_entities,lambda h,p:[PanelScreenshot(h,p)])
