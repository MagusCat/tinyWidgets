"""Regressions for bounded work, independent bindings and editor responsiveness."""
import ast,copy,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from randly_widgets import runtime
from randly_widgets.composer import render
from randly_widgets.editor_worker import EditorWorker
from randly_widgets.jobs import Scheduler
from randly_widgets.stream import JsonCache,frozen_data
from test_widgets import widget

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher=patch('randly_widgets.jobs.RUNTIME',self.temp.name)
        patcher.start();self.addCleanup(patcher.stop)

    def test_large_catalog_uses_three_listeners_not_one_per_instance(self):
        yuck,_=render(widgets=[widget('api'+str(i)) for i in range(100)])
        self.assertEqual(yuck.count('(deflisten '),3)
        self.assertNotIn('wcfg.o[',yuck);self.assertNotIn('wcfg.m[',yuck)
        self.assertIn('woptions[wid]',yuck);self.assertIn('wframes[wid]',yuck)
        import re
        initial=re.search(r'\(deflisten wcfg :initial ("(?:[^"\\]|\\.)*")',yuck)
        self.assertEqual(set(json.loads(json.loads(initial[1]))),{'g','r','t'})

    def test_rapid_editor_requests_run_latest_only_without_blocking_caller(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def execute(mode):
            calls.append(mode)
            if len(calls)==1:entered.set();release.wait(2)
            return True
        worker=EditorWorker('/tmp/example',lambda:({},{}),execute)
        try:
            worker.request(1);self.assertTrue(entered.wait(2))
            for i in range(2,102):worker.request(i)
            self.assertEqual(calls,[1]);self.assertTrue(worker.take()[1])
            release.set()
            deadline=time.monotonic()+2
            while len(calls)<2 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(calls,[1,101])
        finally:release.set();worker.stop()
        self.assertFalse(worker.thread.is_alive())

    def test_geometry_queries_are_off_the_gtk_thread_and_keep_only_latest_sample(self):
        sampled=threading.Event();ident=[]
        def sample():ident.append(threading.get_ident());sampled.set();return {'geometry':1}
        worker=EditorWorker('/tmp/example',sample,lambda _:True)
        try:
            self.assertTrue(sampled.wait(2))
            self.assertNotEqual(ident[0],threading.get_ident())
            self.assertEqual(worker.take()[0][0],{'geometry':1})
            self.assertIsNone(worker.take()[0])
        finally:worker.stop()

    def test_cached_large_data_is_not_decoded_at_frame_rate(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'data.json';path.write_text(json.dumps({'text':'x'*200000}))
            cache=JsonCache()
            with patch('randly_widgets.stream.read_json',wraps=__import__('randly_widgets.stream',fromlist=['read_json']).read_json) as read:
                for _ in range(100):self.assertEqual(len(cache.read(path,{})['text']),200000)
                self.assertEqual(read.call_count,1)
                path.write_text('{"new":true}');self.assertEqual(cache.read(path,{}),{'new':True})
                self.assertEqual(read.call_count,2)

    def test_empty_success_ipc_never_resets_widgets(self):
        with patch.object(runtime,'eww',return_value=SimpleNamespace(returncode=0,stdout='')) as client,patch.object(runtime.time,'sleep'):
            self.assertFalse(runtime.prime_data([widget()]))
            self.assertEqual(client.call_count,3)
            self.assertTrue(all(c.args==('get','wcfg') for c in client.call_args_list))

    def test_freeze_from_old_workspace_cannot_replace_current_data(self):
        data={'a':{'pct':90}};freeze={'a':{'token':'old','data':{'pct':10}}}
        self.assertEqual(frozen_data(data,{'a':{'token':'new'}},freeze),data)
        self.assertEqual(frozen_data(data,{'a':{'token':'old'}},freeze),{'a':{'pct':10}})

    def test_editing_and_style_changes_do_not_rerun_providers(self):
        registry=SimpleNamespace(modules={'example':{'provider':'provider.py','execution':'inline','interval':60}},missing={})
        provider=SimpleNamespace(collect=lambda _: {'count':1})
        scheduler=Scheduler(registry);w=widget('a',kind='example')
        with patch('randly_widgets.jobs.load_provider',return_value=provider) as loader:
            first={'skin':'bento','is_editing':'no','anim_class':'','width':'100'}
            scheduler.tick([w],lambda _:first,now=0)
            scheduler.tick([w],lambda _:{**first,'skin':'retro','is_editing':'yes','anim_class':'editing'},now=1)
            self.assertEqual(loader.call_count,1)
        scheduler.close()

    def test_100_worker_widgets_still_have_only_four_concurrent_jobs(self):
        registry=SimpleNamespace(modules={'example':{'provider':'provider.py','execution':'worker','interval':60}},missing={})
        scheduler=Scheduler(registry)
        process=SimpleNamespace(start=lambda:None,is_alive=lambda:True)
        connection=SimpleNamespace(close=lambda:None,poll=lambda:False)
        context=SimpleNamespace(Pipe=lambda **_: (connection,connection),Process=lambda **_: process)
        with patch('randly_widgets.jobs.multiprocessing.get_context',return_value=context):
            scheduler.tick([widget('a'+str(i),kind='example') for i in range(100)],lambda _:{},now=0)
            self.assertEqual(len(scheduler.jobs),4)

    def test_option_edit_preserves_unchanged_anchor_and_only_moves_changed_instance(self):
        # Load the pure interaction method without importing the GTK display package.
        path=Path(__file__).parents[1]/'editor/interaction.py'
        tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='store_changed_positions')
        namespace={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(path),'exec'),namespace)
        calls=[];rects={'a':[10,10,100,100],'b':[20,20,100,100]}
        editor=SimpleNamespace(widgets=[widget('a'),widget('b')],rects=copy.deepcopy(rects),saved_rects=copy.deepcopy(rects),to_conf=lambda w,r:calls.append(w['id']))
        namespace['store_changed_positions'](editor);self.assertEqual(calls,[])
        editor.rects['b'][0]+=10
        namespace['store_changed_positions'](editor);self.assertEqual(calls,['b'])

    def test_stale_editor_flags_are_cleaned_only_without_a_live_editor(self):
        import fcntl
        with tempfile.TemporaryDirectory() as td,patch.object(runtime,'RUNTIME',td):
            root=Path(td);flag=root/'eww-widgets-editing';flag.touch()
            with (root/'eww-widget-editor.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                runtime.clear_stale_editor();self.assertTrue(flag.exists())
            runtime.clear_stale_editor();self.assertFalse(flag.exists())

    def test_shared_settings_are_read_once_for_a_hundred_instances(self):
        from randly_widgets import appearance
        from randly_widgets.stream import Configuration
        with patch('randly_widgets.stream.load',return_value=[widget('a'+str(i)) for i in range(100)]),patch.object(appearance,'load_style',wraps=appearance.load_style) as style,patch.object(appearance,'load_animation',wraps=appearance.load_animation) as animation:
            cfg=Configuration();cfg.refresh();cfg.refresh()
            self.assertEqual(len(cfg.opts),100)
            self.assertEqual(style.call_count,1);self.assertEqual(animation.call_count,1)

    def test_editor_stop_cancels_pending_mailbox_request_without_a_process(self):
        from randly_widgets.editor_mailbox import SyncMailbox
        with tempfile.TemporaryDirectory() as td,patch('subprocess.Popen',side_effect=AssertionError('No per-action process')):
            mailbox=SyncMailbox(td);mailbox.heartbeat()
            worker=EditorWorker('/tmp/example',lambda:{},mailbox=mailbox)
            try:
                worker.request(1);deadline=time.monotonic()+2
                while not mailbox.request_path.exists() and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(mailbox.request_path.exists())
            finally:worker.stop()
            self.assertFalse(worker.thread.is_alive());self.assertFalse(mailbox.request_path.exists())

    def test_start_has_a_single_initial_reconciliation_owner(self):
        from randly_widgets import cli
        with patch('randly_widgets.paths.ensure_runtime'),patch.object(runtime,'clear_stale_editor') as cleanup,patch('randly_widgets.adapters.eww.start',return_value=True),patch.object(runtime,'sync') as sync,patch.object(cli,'start_watcher') as watcher,patch('randly_widgets.policy.is_disabled',return_value=False),patch.dict('os.environ',{'WAYFIRE_SOCKET':'/tmp/example.sock'}):
            self.assertEqual(cli.main(['start']),0)
            cleanup.assert_called_once();watcher.assert_called_once();sync.assert_not_called()
