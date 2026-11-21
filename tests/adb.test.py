"""ADB routing, command isolation and installation against a fake Android transport."""
import asyncio
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.exceptions import TcpTimeoutException

_pkg=types.ModuleType('aurelvi_pkg');_pkg.__path__=[str(Path(__file__).resolve().parents[1]/'custom_components/aurelvi')];sys.modules['aurelvi_pkg']=_pkg
spec=importlib.util.spec_from_file_location('aurelvi_pkg.adb',Path(__file__).resolve().parents[1]/'custom_components/aurelvi/adb.py')
adb=importlib.util.module_from_spec(spec);sys.modules['aurelvi_pkg.adb']=adb;spec.loader.exec_module(adb)

class Device:
    instances=[]
    fail_install=False
    def __init__(self,*a,**kw):self.commands=[];self.shell_options={};self.closed=False;self.instances.append(self)
    def connect(self,**kw):return True
    def shell(self,cmd,**kw):
        self.commands.append(cmd)
        self.shell_options[cmd] = kw
        if cmd.startswith('pm install'):return 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]' if self.fail_install else 'Success'
        if 'query-activities' in cmd:return 'sk.openpanel.nspanel/.MainActivity\ncom.android.launcher3/.Launcher\n'
        return 'OK'
    def push(self,local,remote,**kw):assert Path(local).exists();self.remote=remote;self.push_options=kw
    def close(self):self.closed=True

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.key=str(Path(self.tmp.name)/'adbkey')
        self.p=patch.dict(sys.modules,{'adb_shell.adb_device':types.SimpleNamespace(AdbDeviceTcp=Device)})
        self.p.start();self.addCleanup(self.p.stop)
    def execute(self,op,data=None):return adb.execute(self.key,'192.168.1.231',5555,op,data or {})
    def test_local_endpoint(self):self.assertEqual(adb.endpoint({'host':'192.168.1.231','port':5555}),('192.168.1.231',5555))
    def test_reject_non_panel_targets(self):
        for host in ['127.0.0.1','0.0.0.0','169.254.169.254','8.8.8.8','localhost','192.168.1.2;reboot','224.0.0.1']:
            with self.subTest(host=host),self.assertRaises(ValueError):adb.endpoint({'host':host})
    def test_reject_ports(self):
        for port in [0,65536,'invalid',None]:
            with self.subTest(port=port),self.assertRaises(ValueError):adb.endpoint({'host':'192.168.1.2','port':port})
    def test_text_never_accepts_shell(self):
        for text in ['hello;reboot','$(reboot)','`reboot`','a\nb','a%sb','á','']:
            with self.subTest(text=text),self.assertRaises(ValueError):adb.text_command(text)
        self.assertEqual(adb.text_command('hello world!'),'input text '+"'hello%sworld!'")
    def test_connect_key_persisted_private_and_transport_closed(self):
        self.execute('connect');key=Path(self.key).read_bytes();self.execute('wake')
        self.assertEqual(key,Path(self.key).read_bytes())
        if os.name == 'posix':
            self.assertEqual(Path(self.key).stat().st_mode & 0o777, 0o600)
        self.assertTrue(Device.instances[-1].closed);self.assertEqual(Device.instances[-1].commands,['input keyevent 224'])
    def test_restore_resolves_alternate_home(self):
        self.execute('unset_home');self.assertEqual(Device.instances[-1].commands[-1],'cmd package set-home-activity com.android.launcher3/.Launcher')
    def test_install_checks_result_then_launches_and_cleans(self):
        def download(path):Path(path).write_bytes(b'APK');return 'Aurelvi-0.3.4.apk'
        with patch.object(adb,'download_apk',download):result=self.execute('install')
        self.assertIn('installed',result['output']);d=Device.instances[-1]
        self.assertEqual(d.commands,['pm install -r /data/local/tmp/aurelvi-update.apk','am start -n sk.openpanel.nspanel/.MainActivity','rm -f /data/local/tmp/aurelvi-update.apk']);self.assertTrue(d.closed)
        self.assertEqual(d.push_options, {'transport_timeout_s': 120, 'read_timeout_s': 120, 'progress_callback': None})
        self.assertEqual(d.shell_options[d.commands[0]], {
            'transport_timeout_s': 180, 'read_timeout_s': 180, 'timeout_s': 180,
        })

    def test_install_timeout_reports_the_failed_stage_and_does_not_reinstall(self):
        def download(path):
            Path(path).write_bytes(b'APK')
            return 'Aurelvi-0.3.17.apk'

        original_shell = Device.shell

        def slow_install(device, command, **options):
            if command.startswith('pm install'):
                device.commands.append(command)
                raise TcpTimeoutException('no install result')
            return original_shell(device, command, **options)

        with patch.object(adb, 'download_apk', download):
            with patch.object(Device, 'push', side_effect=TcpTimeoutException('no transfer acknowledgment')):
                with self.assertRaisesRegex(ValueError, 'backend.adb.transfer_timeout'):
                    self.execute('install')
                self.assertEqual(Device.instances[-1].commands, ['rm -f /data/local/tmp/aurelvi-update.apk'])
            with patch.object(Device, 'shell', slow_install):
                with self.assertRaisesRegex(ValueError, 'backend.adb.install_timeout'):
                    self.execute('install')
                device = Device.instances[-1]
                self.assertEqual(device.commands, [
                    'pm install -r /data/local/tmp/aurelvi-update.apk',
                    'rm -f /data/local/tmp/aurelvi-update.apk',
                ])
                self.assertTrue(device.closed)

    def test_install_progress_uses_actual_bytes_and_indeterminate_android_stage(self):
        payload = b'x' * 131072
        asset = {'name': 'Aurelvi-0.3.17.apk', 'size': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(),
                 'browser_download_url': 'https://github.com/soso8782/aurelvi-apk/releases/download/v0.3.17/Aurelvi-0.3.17.apk'}
        replies = iter([json.dumps({'assets': [asset]}).encode(), payload])
        events = []
        def report(phase, percent=None):
            events.append((phase, percent))

        def push(device, local, remote, *, progress_callback, **_timeouts):
            self.assertEqual(Path(local).stat().st_size, len(payload))
            for chunk in (32768, 32768, 65536):
                progress_callback(remote, chunk, len(payload))

        with patch.object(adb, 'urlopen', lambda *a, **kw: io.BytesIO(next(replies))), patch.object(Device, 'push', push):
            adb.execute(self.key, '192.168.1.231', 5555, 'install', {}, report)
        self.assertEqual(events, [
            ('download', None), ('download', 50), ('download', 99), ('download', 100),
            ('transfer', 0), ('transfer', 25), ('transfer', 50), ('transfer', 99),
            ('install', None), ('launch', None),
        ])

    def test_progress_is_available_while_the_adb_worker_is_running(self):
        async def run():
            started = asyncio.Event()
            finish = asyncio.Event()
            async def executor(*args):
                args[-1]('transfer', 63)
                await asyncio.sleep(0)
                started.set()
                await finish.wait()
                return {'output': 'done'}

            hass = types.SimpleNamespace(async_add_executor_job=executor, config=types.SimpleNamespace(path=lambda *args: self.key))
            hub = self.hub(hass=hass)
            task = asyncio.create_task(adb.async_command(hub, {'operation': 'install', 'host': '192.168.1.2',
                                                               'progress_id': 'progress-test'}))
            await started.wait()
            try:
                self.assertEqual(hub.adb_install_progress, {'id': 'progress-test', 'phase': 'transfer', 'percent': 63})
            finally:
                finish.set()
                self.assertEqual(await task, {'output': 'done'})
            self.assertIsNone(hub.adb_install_progress)
        asyncio.run(run())
    def test_failed_install_does_not_launch(self):
        with patch.object(Device,'fail_install',True),patch.object(adb,'download_apk',lambda path:Path(path).write_bytes(b'APK')):
            with self.assertRaisesRegex(ValueError,'INSTALL_FAILED'):self.execute('install')
        self.assertFalse(any(c.startswith('am start') for c in Device.instances[-1].commands));self.assertTrue(Device.instances[-1].closed)
    def test_install_stops_before_requesting_new_adb_authorization(self):
        def unauthorized(device, **kwargs):
            kwargs['auth_callback'](device)
            self.fail('ADB enrollment would open a prompt on the panel')
        with patch.object(Device, 'connect', unauthorized), patch.object(adb, 'download_apk') as download:
            with self.assertRaisesRegex(ValueError, 'install_needs_authorization'):
                self.execute('install')
        download.assert_not_called()
        self.assertTrue(Device.instances[-1].closed)

    def test_connection_errors_identify_the_failed_stage(self):
        cases = [
            (ConnectionRefusedError('closed'), False, 'backend.adb.port_refused'),
            (TcpTimeoutException('no reply'), False, 'backend.adb.connect_timeout'),
            (TcpTimeoutException('no approval'), True, 'backend.adb.auth_pending'),
        ]
        for error, offered_key, expected in cases:
            with self.subTest(error=error):
                def fail(device, **kwargs):
                    if offered_key:
                        kwargs['auth_callback'](device)
                    raise error

                with patch.object(Device, 'connect', fail), self.assertRaises(ValueError) as caught:
                    self.execute('connect')
                self.assertEqual(str(caught.exception).partition('|')[0], expected)
                self.assertTrue(Device.instances[-1].closed)

    def test_install_reports_success_when_opening_the_app_fails(self):
        def download(path):
            Path(path).write_bytes(b'APK')
            return 'Aurelvi-0.3.17.apk'
        def launch_fails(device, command, **kwargs):
            device.commands.append(command)
            return 'Error: Activity not found' if command.startswith('am start') else 'Success'
        with patch.object(adb, 'download_apk', download), patch.object(Device, 'shell', launch_fails):
            self.assertIn('installed_launch_failed', self.execute('install')['output'])
        self.assertTrue(Device.instances[-1].closed)

    def test_download_integrity(self):
        payload=b'APK';asset={'name':'Aurelvi-0.3.4.apk','browser_download_url':'https://github.com/soso8782/aurelvi-apk/releases/download/v0.3.4/Aurelvi-0.3.4.apk','digest':'sha256:'+hashlib.sha256(payload).hexdigest(),'size':3}
        def run(blob):
            replies=iter([json.dumps({'assets':[asset]}).encode(),blob])
            with patch.object(adb,'urlopen',lambda *a,**kw:io.BytesIO(next(replies))):return adb.download_apk(str(Path(self.tmp.name)/'file.apk'))
        self.assertEqual(run(payload),asset['name'])
        with self.assertRaisesRegex(ValueError,'apk_mismatch'):run(b'BAD')
    def test_unknown_operation_does_not_connect(self):
        with self.assertRaises(ValueError):asyncio.run(adb.async_command(None,{'operation':'shell','host':'192.168.1.2'}))
    def test_busy_lock_rejects_concurrent_commands(self):
        async def run():
            hub=types.SimpleNamespace(adb_lock=asyncio.Lock());await hub.adb_lock.acquire()
            with self.assertRaisesRegex(ValueError,'adb.busy'):await adb.async_command(hub,{'operation':'connect','host':'192.168.1.2'})
        asyncio.run(run())

    def test_cancelled_caller_keeps_adb_locked_until_install_finishes(self):
        async def run():
            started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
            async def executor(*args):
                started.set()
                await release.wait()
                finished.set()
                return {'output': 'Success'}
            hass = types.SimpleNamespace(async_add_executor_job=executor, config=types.SimpleNamespace(path=lambda *args: self.key))
            hub = self.hub(hass=hass)
            data = {'operation': 'install', 'host': '192.168.1.2'}
            first = asyncio.create_task(adb.async_command(hub, data))
            await started.wait()
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            try:
                with self.assertRaisesRegex(ValueError, 'adb.busy'):
                    await adb.async_command(hub, data)
            finally:
                release.set()
                await finished.wait()
            self.assertFalse(hub.adb_lock.locked())
        asyncio.run(run())

    def hub(self,**kw):
        h=types.SimpleNamespace(panels={'p1':{'paired':True}},status={},calls=[],hass=None)
        async def persist():h.calls.append('persist')
        h.persist=persist;h.__dict__.update(kw);return h
    def test_resolve_endpoint_order(self):
        h=self.hub();h.status['p1']={'info':{'ip':'192.168.1.50'}}
        self.assertEqual(adb.resolve_endpoint(h,'p1'),('192.168.1.50',5555))
        h.panels['p1']['adb']={'host':'192.168.1.60','port':5556}
        self.assertEqual(adb.resolve_endpoint(h,'p1'),('192.168.1.60',5556))
        self.assertEqual(adb.resolve_endpoint(h,'p1',{'host':'192.168.1.70'}),('192.168.1.70',5556))
        self.assertTrue(adb.has_endpoint(h,'p1'))
    def test_resolve_endpoint_missing_or_public(self):
        h=self.hub();self.assertFalse(adb.has_endpoint(h,'p1'))
        with self.assertRaises(ValueError):adb.resolve_endpoint(h,'p1')
        h.status['p1']={'info':{'ip':'8.8.8.8'}}
        with self.assertRaises(ValueError):adb.resolve_endpoint(h,'p1')
    def test_remember_endpoint_persists_once(self):
        h=self.hub();asyncio.run(adb.remember_endpoint(h,'p1',{'host':'192.168.1.9','port':5555}));asyncio.run(adb.remember_endpoint(h,'p1',{'host':'192.168.1.9','port':5555}))
        self.assertEqual(h.panels['p1']['adb'],{'host':'192.168.1.9','port':5555});self.assertEqual(h.calls,['persist'])
    def test_service_rejects_disallowed_operations(self):
        h=self.hub();h.panels['p1']['adb']={'host':'192.168.1.9','port':5555}
        for op in ['install','text','set_home','unset_home','memory','notifications','shell',None]:
            with self.subTest(op=op),self.assertRaisesRegex(ValueError,'operation_not_allowed'):asyncio.run(adb.async_service(h,{'panel_id':'p1','operation':op}))
        with self.assertRaisesRegex(ValueError,'unknown_panel'):asyncio.run(adb.async_service(h,{'panel_id':'zz','operation':'reboot'}))
    def test_service_runs_reboot_with_resolved_endpoint(self):
        h=self.hub();h.status['p1']={'info':{'ip':'192.168.1.50'}};seen=[]
        async def fake(hub,data):seen.append(data);return {'output':'OK'}
        with patch.object(adb,'async_command',fake):asyncio.run(adb.async_service(h,{'panel_id':'p1','operation':'reboot'}))
        self.assertEqual(seen,[{'operation':'reboot','host':'192.168.1.50','port':5555}]);self.assertEqual(h.panels['p1']['adb']['host'],'192.168.1.50')

if __name__=='__main__':unittest.main()
