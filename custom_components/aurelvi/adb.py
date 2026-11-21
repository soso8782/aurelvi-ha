"""Administrator-only ADB setup, without an external ADB executable."""
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
from .i18n import msg
from urllib.request import Request, urlopen

COMPONENT = "sk.openpanel.nspanel/.MainActivity"
APK_REPOSITORY = "soso8782/aurelvi-apk"
COMMANDS = {
    "wake": "input keyevent 224",
    "power": "input keyevent 26",
    "back": "input keyevent 4",
    "home": "input keyevent 3",
    "notifications": "cmd statusbar expand-notifications",
    "memory": "dumpsys meminfo sk.openpanel.nspanel",
    "launch": "am start -n " + COMPONENT,
    "set_home": "cmd package set-home-activity " + COMPONENT,
    "unset_home": "",
    "reboot": "reboot",
    "connect": "getprop ro.product.model",
}
SERVICE_OPERATIONS = ("wake", "power", "back", "home", "launch", "reboot", "connect")
MAX_APK = 64 * 1024 * 1024
APK_TRANSFER_TIMEOUT = 120
APK_INSTALL_TIMEOUT = 180


def endpoint(data):
    try:
        host = str(ipaddress.ip_address(str(data.get("host", "")).strip()))
        address = ipaddress.ip_address(host)
        if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValueError()
        port = int(data.get("port", 5555))
        if not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(msg('backend.adb.invalid_endpoint')) from None
    return host, port


def resolve_endpoint(hub, pid, data=None):
    """Return a validated (host, port): explicit data, then stored, then the MQTT-reported IP."""
    data = data or {}
    stored = hub.panels.get(pid, {}).get("adb") or {}
    reported = hub.status.get(pid, {}).get("info", {}).get("ip")
    host = data.get("host") or stored.get("host") or reported
    port = data.get("port") or stored.get("port") or 5555
    if not host:
        raise ValueError(msg('backend.adb.no_address'))
    return endpoint({"host": host, "port": port})


def has_endpoint(hub, pid):
    try:
        resolve_endpoint(hub, pid)
    except ValueError:
        return False
    return True


async def remember_endpoint(hub, pid, data):
    """Persist the endpoint of a panel after a successful ADB operation."""
    host, port = endpoint(data)
    panel = hub.panels.get(pid)
    if panel is not None and panel.get("adb") != {"host": host, "port": port}:
        panel["adb"] = {"host": host, "port": port}
        await hub.persist()


async def async_service(hub, data):
    """Service entry point: only non-destructive operations, endpoint resolved per panel."""
    pid = data.get("panel_id")
    operation = data.get("operation")
    if operation not in SERVICE_OPERATIONS:
        raise ValueError(msg('backend.adb.operation_not_allowed', operation=operation))
    if pid not in hub.panels:
        raise ValueError(msg('backend.adb.unknown_panel'))
    host, port = resolve_endpoint(hub, pid, data)
    result = await async_command(hub, {"operation": operation, "host": host, "port": port})
    await remember_endpoint(hub, pid, {"host": host, "port": port})
    return result


async def async_install_latest(hub, pid):
    """Install the official APK on a paired panel through its ADB connection."""
    if not hub.panels.get(pid, {}).get("paired"):
        raise ValueError(msg("backend.adb.unknown_panel"))
    host, port = resolve_endpoint(hub, pid)
    result = await async_command(hub, {"operation": "install", "host": host, "port": port})
    await remember_endpoint(hub, pid, {"host": host, "port": port})
    return result


def text_command(text):
    # Android input text is ASCII-only; never pass shell syntax from the UI.
    if not isinstance(text, str) or not 1 <= len(text) <= 200 or not re.fullmatch(r"[A-Za-z0-9 .,!?@_+:/=-]+", text):
        raise ValueError(msg('backend.adb.text_invalid'))
    return "input text " + shlex.quote(text.replace(" ", "%s"))


def reject_unauthorized_install(_transport):
    """Abort before adb-shell asks the device to authorize a new key."""
    raise ValueError(msg("backend.adb.install_needs_authorization"))


def download_apk(path):
    """Resolve only the official stable public Aurelvi release, bounded in size."""
    headers = {"User-Agent": "Aurelvi-ADB", "Accept": "application/vnd.github+json"}
    with urlopen(Request(f"https://api.github.com/repos/{APK_REPOSITORY}/releases/latest", headers=headers), timeout=30) as response:
        raw = response.read(1048577)
    if len(raw) > 1048576:
        raise ValueError(msg('backend.adb.release_too_large'))
    release = json.loads(raw)
    if release.get("draft") or release.get("prerelease"):
        raise ValueError(msg('backend.adb.no_stable_release'))
    assets = [a for a in release.get("assets", []) if re.fullmatch(r"Aurelvi-[0-9]+\.[0-9]+\.[0-9]+\.apk", a.get("name", ""))]
    if len(assets) != 1:
        raise ValueError(msg('backend.adb.release_asset_count'))
    asset = assets[0]
    url = asset.get("browser_download_url", "")
    if not re.fullmatch(rf"https://github\.com/{re.escape(APK_REPOSITORY)}/releases/download/[^/]+/Aurelvi-[0-9.]+\.apk", url):
        raise ValueError(msg('backend.adb.invalid_download_url'))
    digest = asset.get("digest", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError(msg('backend.adb.no_checksum'))
    checksum = hashlib.sha256()
    size = 0
    with urlopen(Request(url, headers={"User-Agent": "Aurelvi-ADB"}), timeout=45) as response, open(path, "wb") as out:
        while chunk := response.read(65536):
            size += len(chunk)
            if size > MAX_APK:
                raise ValueError(msg('backend.adb.apk_too_large'))
            checksum.update(chunk)
            out.write(chunk)
    if not size or size != asset.get("size") or checksum.hexdigest() != digest[7:]:
        raise ValueError(msg('backend.adb.apk_mismatch'))
    return asset["name"]


def execute(key_path, host, port, operation, data):
    from adb_shell.adb_device import AdbDeviceTcp
    from adb_shell.auth.keygen import keygen
    from adb_shell.auth.sign_pythonrsa import PythonRSASigner
    from adb_shell.exceptions import AdbTimeoutError, TcpTimeoutException

    key = Path(key_path)
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        with tempfile.TemporaryDirectory(prefix="aurelvi-key-", dir=key.parent) as folder:
            temporary = str(Path(folder) / "adbkey")
            keygen(temporary)
            os.chmod(temporary, 0o600)
            os.replace(temporary + ".pub", str(key) + ".pub")
            os.replace(temporary, key)
    os.chmod(key, 0o600)
    signer = PythonRSASigner.FromRSAKeyPath(str(key))
    device = AdbDeviceTcp(host, port, default_transport_timeout_s=15)
    awaiting_authorization = False
    timeout_errors = (AdbTimeoutError, TcpTimeoutException, TimeoutError)

    def mark_authorization_prompt(_transport):
        nonlocal awaiting_authorization
        awaiting_authorization = True

    try:
        auth_callback = reject_unauthorized_install if operation == "install" else mark_authorization_prompt
        try:
            connected = device.connect(rsa_keys=[signer], auth_timeout_s=15, read_timeout_s=20, auth_callback=auth_callback)
        except ConnectionRefusedError as err:
            raise ValueError(msg("backend.adb.port_refused", host=host, port=port)) from err
        except timeout_errors as err:
            if awaiting_authorization:
                raise ValueError(msg("backend.adb.auth_pending")) from err
            raise ValueError(msg("backend.adb.connect_timeout", host=host, port=port)) from err
        if not connected:
            raise ValueError(msg('backend.adb.auth_pending'))
        if operation == "install":
            with tempfile.TemporaryDirectory(prefix="aurelvi-apk-") as folder:
                local = str(Path(folder) / "aurelvi.apk")
                try:
                    name = download_apk(local)
                except OSError as err:
                    raise ValueError(msg("backend.adb.download_failed", error=type(err).__name__)) from err
                remote = "/data/local/tmp/aurelvi-update.apk"
                try:
                    # adb-shell applies the TCP timeout before the overall read
                    # deadline. Android may stay quiet while copying or installing.
                    try:
                        device.push(local, remote, transport_timeout_s=APK_TRANSFER_TIMEOUT,
                                    read_timeout_s=APK_TRANSFER_TIMEOUT)
                    except timeout_errors as err:
                        raise ValueError(msg("backend.adb.transfer_timeout", seconds=APK_TRANSFER_TIMEOUT)) from err
                    try:
                        output = device.shell("pm install -r " + remote, transport_timeout_s=APK_INSTALL_TIMEOUT,
                                              read_timeout_s=APK_INSTALL_TIMEOUT, timeout_s=APK_INSTALL_TIMEOUT)
                    except timeout_errors as err:
                        raise ValueError(msg("backend.adb.install_timeout", seconds=APK_INSTALL_TIMEOUT)) from err
                    if not any(line.strip() == "Success" for line in output.splitlines()) or "Failure" in output:
                        raise ValueError(msg('backend.adb.install_failed', output=output[:1000]))
                    try:
                        launch = device.shell(COMMANDS["launch"], read_timeout_s=20)
                    except Exception as err:
                        return {"output": msg("backend.adb.installed_launch_failed", name=name, error=type(err).__name__)}
                    if re.search(r"\b(?:Error|Exception)\b", launch):
                        return {"output": msg("backend.adb.installed_launch_failed", name=name, error=launch[:500])}
                    return {"output": msg('backend.adb.installed', name=name)}
                finally:
                    try:
                        device.shell("rm -f " + remote)
                    except Exception:
                        pass
        if operation == "unset_home":
            homes = device.shell("cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME")
            candidates = [line.strip() for line in homes.splitlines() if re.fullmatch(r"[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+", line.strip()) and not line.strip().startswith("sk.openpanel.nspanel/")]
            if not candidates:
                raise ValueError(msg('backend.adb.no_launcher'))
            command = "cmd package set-home-activity " + shlex.quote(candidates[0])
        else:
            command = text_command(data.get("text")) if operation == "text" else COMMANDS[operation]
        try:
            output = device.shell(command, read_timeout_s=30)
        except Exception:
            if operation == "reboot":
                return {"output": msg('backend.adb.reboot_requested')}
            raise
        if "Error" in output or "Exception" in output or "Unknown command" in output:
            raise ValueError(msg('backend.adb.command_error', output=output[:2000]))
        return {"output": output[:12000] or "OK"}
    finally:
        device.close()


async def async_command(hub, data):
    operation = data.get("operation", "connect")
    if operation not in COMMANDS and operation not in {"text", "install"}:
        raise ValueError(msg('backend.adb.unsupported_operation'))
    host, port = endpoint(data)
    if operation == "text":
        text_command(data.get("text"))
    if not hasattr(hub, "adb_lock"):
        hub.adb_lock = asyncio.Lock()
    async def run():
        if hub.adb_lock.locked():
            raise ValueError(msg('backend.adb.busy'))
        async with hub.adb_lock:
            try:
                return await hub.hass.async_add_executor_job(execute, hub.hass.config.path(".storage", "aurelvi_adbkey"), host, port, operation, data)
            except ValueError:
                raise
            except Exception as err:
                raise ValueError(msg('backend.adb.connection_failed', error=type(err).__name__)) from err

    # Keep the device locked until the executor finishes, even if Studio disconnects.
    job = asyncio.create_task(run())
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        job.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)
        raise
