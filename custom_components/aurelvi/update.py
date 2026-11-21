import re
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.update import UpdateEntity,UpdateEntityFeature
from .adb import APK_REPOSITORY, async_install_latest
from .const import DOMAIN
from .entity import AurelviEntity,add_dynamic
from .i18n import msg, plain
class PanelUpdate(AurelviEntity,UpdateEntity):
    _attr_supported_features=UpdateEntityFeature.INSTALL|UpdateEntityFeature.RELEASE_NOTES
    _attr_title='Aurelvi Panel'
    def __init__(self,h,p):super().__init__(h,p,'update','Aktualizácia aplikácie')
    @property
    def installed_version(self):
        value=self.hub.status.get(self.pid,{}).get('info',{}).get('version','')
        match=re.search(r'\d+\.\d+\.\d+',value)
        return match.group(0) if match else None
    @property
    def latest_version(self):return self.hub.latest.get('version') or self.installed_version
    @property
    def release_url(self):return self.hub.latest.get('release_url')
    async def async_release_notes(self):return self.hub.latest.get('summary','')
    async def async_install(self,version=None,backup=False,**kwargs):
        if not self.hub.latest.get('url'):raise HomeAssistantError(translation_domain=DOMAIN,translation_key='github_not_configured')
        if self.hub.settings.get("githubRepo", "").lower() != APK_REPOSITORY:
            await self.hub.command(self.pid, "update", {"url": self.hub.latest["url"]})
            return
        user_id = getattr(self._context, "user_id", None)
        try:
            if user_id is not None:
                user = await self.hass.auth.async_get_user(user_id)
                if user is None or not user.is_admin:
                    raise ValueError(msg("backend.adb.admin_required"))
            await async_install_latest(self.hub, self.pid)
        except ValueError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="adb_failed",
                                     translation_placeholders={"error": plain(err)}) from err
async def async_setup_entry(hass,entry,async_add_entities):await add_dynamic(hass,entry,async_add_entities,lambda h,p:[PanelUpdate(h,p)])
