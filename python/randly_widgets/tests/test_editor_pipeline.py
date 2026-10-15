"""Persistent reconciliation, bounded drawing and drag leases without Wayland."""
import ast,copy,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from randly_widgets.editor_mailbox import SyncMailbox
from randly_widgets.editor_worker import EditorWorker
from randly_widgets.editor_activity import DragLease,dragging,hold_data,paused_instances
from randly_widgets.editor_paint import GridCache,widget_bounds,union,pixel_bounds,intersects
from randly_widgets.jobs import Scheduler
from test_widgets import widget

class MailboxTests(unittest.TestCase):
    def test_transport_reuses_service_without_spawning_a_process(self):
        with tempfile.TemporaryDirectory() as td,patch('subprocess.Popen',side_effect=AssertionError('No new process')):
            mailbox=SyncMailbox(td);mailbox.heartbeat();(Path(td)/'eww-widgets-editing').touch()
            worker=EditorWorker('/tmp/example',lambda:{},mailbox=mailbox)
            tokens=[]
            try:
                for mode in (1,'global',2):
                    worker.request(mode);deadline=time.monotonic()+2;request=None
                    while time.monotonic()<deadline:
                        request=mailbox.pending()
                        if request:break
                        time.sleep(.005)
                    self.assertIsNotNone(request);self.assertEqual(request['mode'],mode)
                    tokens.append(request['token']);mailbox.complete(request,True)
                    while worker.take()[1] and time.monotonic()<deadline:time.sleep(.005)
                    self.assertFalse(worker.take()[1])
                self.assertEqual(len(set(tokens)),3)
            finally:worker.stop()

    def test_existing_watcher_dispatches_and_acknowledges_editor_request(self):
        import socket
        from randly_widgets import watcher
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'eww-widgets-editing').write_text('global')
            mailbox=SyncMailbox(td);request=mailbox.submit('global');calls=[];deadline=time.monotonic()+2
            connection=SimpleNamespace(settimeout=lambda _:None,close=lambda:None)
            def recv(_):
                calls.append(1)
                if len(calls)==1:return {}
                if mailbox.read(mailbox.ack_path).get('token')==request['token']:raise SystemExit(0)
                if time.monotonic()>deadline:raise AssertionError('Watcher did not acknowledge editor')
                time.sleep(.005);raise socket.timeout()
            with patch.object(watcher,'RUNTIME',td),patch('randly_widgets.editor_mailbox.RUNTIME',td),patch.object(watcher,'lock_or_exit',return_value=0),patch.object(watcher,'connect',return_value=connection),patch.object(watcher,'conf_mtime',return_value=1),patch.object(watcher,'wf_send'),patch.object(watcher,'wf_recv',side_effect=recv),patch('randly_widgets.workspace_guard.invalidate',return_value={'ready_at':0}),patch('randly_widgets.runtime.sync',return_value=True) as reconcile,patch.dict('os.environ',{'WAYFIRE_SOCKET':'/tmp/mock.sock'}):
                with self.assertRaises(SystemExit):watcher.main()
            reconcile.assert_any_call('global',request_token=request['token'])
            self.assertTrue(mailbox.read(mailbox.ack_path)['success']);self.assertTrue(mailbox.available())

    def test_latest_token_cancels_earlier_request_and_cleanup_preserves_newer(self):
        with tempfile.TemporaryDirectory() as td:
            mailbox=SyncMailbox(td);(Path(td)/'eww-widgets-editing').touch()
            first=mailbox.submit(1);second=mailbox.submit('global')
            self.assertFalse(mailbox.current(first['token']));self.assertTrue(mailbox.current(second['token']))
            mailbox.cancel(first['token']);self.assertEqual(mailbox.pending(),second)
            mailbox.complete(first,True);self.assertEqual(mailbox.pending(),second)
            mailbox.complete(second,True);self.assertIsNone(mailbox.pending())

    def test_expired_crashed_or_invalid_requests_do_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            mailbox=SyncMailbox(td);request=mailbox.submit(1)
            self.assertIsNone(mailbox.pending())  # Editor is not running.
            (Path(td)/'eww-widgets-editing').touch()
            for expiry in (0,'later',float('nan'),float('inf')):
                mailbox.request_path.write_text(json.dumps(dict(request,expires=expiry)))
                self.assertIsNone(mailbox.pending())
            for mode in (None,0,-1,101,{},'all'):
                with self.assertRaises(ValueError):mailbox.submit(mode)

    def test_service_restart_or_expired_heartbeat_does_not_spawn_a_fallback(self):
        with tempfile.TemporaryDirectory() as td,patch('subprocess.Popen',side_effect=AssertionError('No fallback process')):
            mailbox=SyncMailbox(td);worker=EditorWorker('/tmp/example',lambda:{},mailbox=mailbox)
            try:self.assertFalse(worker._execute(1));self.assertFalse(mailbox.request_path.exists())
            finally:worker.stop()

    def test_obsolete_request_cannot_close_existing_workspace_widgets(self):
        from contextlib import ExitStack
        from test_motion_regressions import ReconcileTests
        from randly_widgets import runtime
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            root=Path(td);widgets=[widget('global',workspace='Global'),widget('local',workspace='Workspace 1')]
            state=ReconcileTests.harness(self,stack,root,widgets,{w['id']:runtime.spec(w) for w in widgets})
            (root/'eww-widgets-editing').write_text('1')
            self.assertFalse(runtime.sync('global',request_token='obsolete'))
            self.assertEqual(state['active'],{'global','local'})
            self.assertFalse(any(c[0]=='close' for c in state['commands']))

class DragTests(unittest.TestCase):
    def test_drag_lease_renews_expires_and_releases_without_configuration_writes(self):
        with tempfile.TemporaryDirectory() as td:
            lease=DragLease(td);lease.update(True,now=1)
            self.assertTrue(dragging(td,now=2));self.assertFalse(dragging(td,now=3))
            original=lease.path.stat().st_mtime_ns;lease.update(True,now=1.1)
            self.assertEqual(lease.path.stat().st_mtime_ns,original)
            lease.update(True,now=2);self.assertTrue(dragging(td,now=3))
            lease.update(False,now=2.1);self.assertFalse(lease.path.exists())
            lease.close()

    def test_freeze_preserves_interactive_widgets_and_releases_latest_data(self):
        widgets=[widget('api'),widget('cat',kind='cat'),widget('tasks',kind='tasks'),widget('timer',kind='timer')]
        paused=paused_instances(widgets,True);self.assertEqual(paused,{'api','cat'})
        old={w['id']:{'n':1} for w in widgets};new={w['id']:{'n':2} for w in widgets}
        frozen=hold_data(new,old,paused)
        self.assertEqual(frozen['api']['n'],1);self.assertEqual(frozen['tasks']['n'],2)
        self.assertEqual(hold_data(new,old,paused_instances(widgets,False)),new)

    def test_paused_provider_is_not_started_until_drag_finishes(self):
        registry=SimpleNamespace(modules={'example':{'provider':'provider.py','execution':'inline','interval':1}},missing={})
        provider=SimpleNamespace(collect=lambda _: {'value':1})
        scheduler=Scheduler(registry)
        with tempfile.TemporaryDirectory() as td,patch('randly_widgets.jobs.RUNTIME',td),patch('randly_widgets.jobs.load_provider',return_value=provider) as load:
            scheduler.tick([widget(kind='example')],lambda _:{},now=1,paused={'a'})
            self.assertEqual(load.call_count,0)
            scheduler.tick([widget(kind='example')],lambda _:{},now=2)
            self.assertEqual(load.call_count,1)
        scheduler.close()

class PaintTests(unittest.TestCase):
    def test_grid_tile_is_cached_small_and_invalidated_by_theme_and_scale(self):
        cache=GridCache();tile=cache.get(20,(.2,.4,.6),2)
        for _ in range(100):self.assertIs(cache.get(20,(.2,.4,.6),2),tile)
        self.assertEqual(cache.builds,1);self.assertEqual(tile.get_width(),40)
        self.assertIsNot(cache.get(20,(.6,.4,.2),2),tile)
        self.assertEqual(cache.builds,2)
        self.assertEqual(cache.get(10,(.6,.4,.2),1).get_width(),10)

    def canvas(self):
        import cairo
        path=Path(__file__).parents[1]/'editor/canvas.py'
        cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef))
        namespace=dict(cairo=cairo,time=time,GridCache=GridCache,widget_bounds=widget_bounds,union=union,pixel_bounds=pixel_bounds,intersects=intersects,
                       W=SimpleNamespace(KINDS={'api':'API'},find=lambda ws,wid:next((w for w in ws if w['id']==wid),None)))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(path),'exec'),namespace)
        editor=namespace['CanvasMixin']();editor.widgets=[widget('left'),widget('right')]
        editor.rects={'left':[80,120,180,110],'right':[1300,120,180,110]};editor.draw_rects=copy.deepcopy(editor.rects)
        editor.area=SimpleNamespace(get_allocation=lambda:SimpleNamespace(width=1920,height=1080),get_scale_factor=lambda:1)
        editor.wa={'x':0,'y':0,'width':1920,'height':1080};editor.prefs={'grid':True,'step':20}
        editor.colors={key:(.4,.5,.6) for key in ('primary','surface','text','muted','tertiary')}
        editor.mapped_ids={'left','right'};editor.style_fx='none';editor.drag=None;editor.hover=None;editor.selected_wid=None
        editor.guides=[];editor.toast=None;editor.mouse=(0,0);editor.is_widget_visible=lambda _:True
        editor.handles=lambda _:{};editor.draw_toolbar=lambda *_:None
        return editor

    def test_partial_repaint_matches_full_render_after_widget_moves(self):
        import cairo
        editor=self.canvas();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,1920,1080);cr=cairo.Context(surface)
        editor.on_draw(None,cr)
        old=list(editor.rects['left']);new=[280,160,180,110]
        damage=union([widget_bounds(r,editor.wa,editor.chip_widths['left']) for r in (old,new)])
        editor.rects['left']=new;editor.draw_rects['left']=new
        cr.save();cr.rectangle(*pixel_bounds(damage));cr.clip();editor.on_draw(None,cr);cr.restore()
        reference=cairo.ImageSurface(cairo.FORMAT_ARGB32,1920,1080);editor.on_draw(None,cairo.Context(reference))
        surface.flush();reference.flush();self.assertEqual(bytes(surface.get_data()),bytes(reference.get_data()))

    def test_clipped_paint_skips_widget_text_outside_damage(self):
        import cairo
        editor=self.canvas();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,1920,1080);cr=cairo.Context(surface)
        editor.on_draw(None,cr)
        text=editor.text;labels=[]
        def record(cr,s,*args,**kw):labels.append(s);return text(cr,s,*args,**kw)
        editor.text=record;cr.rectangle(40,40,400,300);cr.clip();editor.on_draw(None,cr)
        self.assertTrue(any('left' in s for s in labels));self.assertFalse(any('right' in s for s in labels))
