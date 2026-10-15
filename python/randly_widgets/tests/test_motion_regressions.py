"""Movement, stale geometry and entry latency regressions, without a display."""
import ast,copy,json,tempfile,threading,time,unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from randly_widgets import runtime
from randly_widgets.editor_geometry import GeometryTracker
from randly_widgets.transitions import MotionEngine
from test_widgets import widget

class GeometryTests(unittest.TestCase):
    def test_intermediate_allocation_never_expands_a_confirmed_outline(self):
        tracker=GeometryTracker();original=[10,20,300,120]
        tracker.resolve('a',original,original);tracker.resolve('a',original,original)
        self.assertEqual(tracker.resolve('a',[10,20,900,800],original),original)
        self.assertEqual(tracker.resolve('a',original,original),original)
        actual=[10,20,320,150]
        self.assertEqual(tracker.resolve('a',actual,original),original)
        self.assertEqual(tracker.resolve('a',actual,original),actual)

    def test_move_holds_target_against_old_missing_and_transient_samples(self):
        tracker=GeometryTracker();old=[10,20,300,120];target=[500,400,300,120]
        tracker.resolve('a',old,old);tracker.resolve('a',old,old)
        tracker.expect('a',target,now=1)
        for raw in (old,None,[500,400,900,800]):
            self.assertEqual(tracker.resolve('a',raw,old,now=1.5),target)
        self.assertEqual(tracker.resolve('a',target,old,now=1.6),target)
        self.assertNotIn('a',tracker.pending)

    def test_unacknowledged_move_eventually_recovers_real_geometry(self):
        tracker=GeometryTracker();actual=[10,20,300,120];target=[500,400,300,120]
        tracker.resolve('a',actual,actual);tracker.resolve('a',actual,actual)
        tracker.expect('a',target,now=1)
        self.assertEqual(tracker.resolve('a',actual,actual,now=4),actual)
        self.assertNotIn('a',tracker.pending)

    def test_generator_prunes_every_geometry_cache(self):
        tracker=GeometryTracker()
        for wid in ('keep','remove'):
            tracker.resolve(wid,[0,0,300,120],[0,0,300,120]);tracker.resolve(wid,[0,0,300,120],[0,0,300,120]);tracker.expect(wid,[0,0,300,120])
        tracker.prune(wid for wid in ['keep'])
        self.assertEqual(set(tracker.accepted),{'keep'});self.assertEqual(set(tracker.pending),{'keep'})
        self.assertNotIn('remove',tracker.candidates)

    def test_drag_tracks_pointer_without_size_spring_or_overshoot(self):
        path=Path(__file__).parents[1]/'editor/interaction.py';tree=ast.parse(path.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_anim_tick')
        namespace={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(path),'exec'),namespace)
        editor=SimpleNamespace(rects={'a':[500,400,300,120]},draw_rects={'a':[10,20,80,80]},drag=('a','move'),area=SimpleNamespace(queue_draw=lambda:None))
        namespace['_anim_tick'](editor);self.assertEqual(editor.draw_rects['a'],editor.rects['a'])
        editor.drag=None;editor.rects['a']=[800,700,600,200]
        for _ in range(20):
            namespace['_anim_tick'](editor)
            self.assertEqual(editor.draw_rects['a'][2:],[600,200])
            self.assertLessEqual(editor.draw_rects['a'][0],800)

class EntryLatencyTests(unittest.TestCase):
    def test_stable_content_starts_in_less_than_a_tenth_of_a_second(self):
        engine=MotionEngine();control={'a':{'token':'x','reveal':True,'effect':'zap','ms':420}}
        engine.step(control,{'a':{'text':'ready'}},{'a':True},{},0)
        frames,_,_=engine.step(control,{'a':{'text':'ready'}},{'a':True},{},.061)
        self.assertTrue(frames['a']['show'])

    def test_changing_content_has_a_short_bounded_wait(self):
        engine=MotionEngine();control={'a':{'token':'x','reveal':True,'effect':'zap','ms':420}}
        for n in range(26):frames,_,_=engine.step(control,{'a':{'count':n}},{'a':True},{},n*.01)
        self.assertTrue(frames['a']['show'])

    def test_large_entrance_batches_prepare_one_motion_update(self):
        ids=['a'+str(i) for i in range(20)]
        specs={wid:runtime.spec(widget(wid)) for wid in ids}
        with patch.object(runtime,'set_motion',return_value=True) as motion,patch.object(runtime,'eww_open_animated',return_value=True) as opener,patch.object(runtime,'stagger_pause') as pauses:
            runtime.open_widgets(ids,specs,set(),{},dict(runtime.ANIM_DEFAULTS,jitter=0),True,True)
            self.assertEqual(motion.call_count,1)
            self.assertEqual(set(motion.call_args.args[1]),set(ids))
            self.assertTrue(all(call.args[-1] is True for call in opener.call_args_list))
            self.assertLessEqual(sum(call.args[0]['stagger'] for call in pauses.call_args_list),300.001)

    def test_batch_exit_updates_control_once(self):
        with patch.object(runtime,'set_motion',return_value=True) as motion,patch.object(runtime,'eww'),patch.object(runtime,'wf_view_ids',return_value={}):
            runtime.close_widgets(['a','b','c'],{},runtime.ANIM_DEFAULTS,False,False)
            self.assertEqual(motion.call_count,1)
            self.assertEqual(motion.call_args.args[1],['a','b','c'])

class ReconcileTests(unittest.TestCase):
    def harness(self,stack,root,widgets,applied,on_open=None):
        state={'active':set(applied),'commands':[]}
        (root/'conf').write_text('initial');(root/'applied').write_text(json.dumps(applied))
        def client(*args):
            state['commands'].append(args)
            if args[0]=='active-windows':return SimpleNamespace(returncode=0,stdout='\n'.join(wid+': rw-api' for wid in state['active']))
            if args[0]=='open':
                wid=args[args.index('--id')+1];state['active'].add(wid)
                if on_open:on_open(wid)
            if args[0]=='close':state['active'].difference_update(args[1:])
            return SimpleNamespace(returncode=0,stdout='')
        for name,value in [('RUNTIME',str(root)),('LOCK',str(root/'lock')),('CONF',str(root/'conf')),('APPLIED',str(root/'applied'))]:stack.enter_context(patch.object(runtime,name,value))
        for name,value in [('workspace_snapshot',(5,1,0,0,3)),('is_disabled',False),('power_policy',{}),('load',widgets),('prime_data',True),('set_motion',True),('wf_view_ids',{}),('load_animation',dict(runtime.ANIM_DEFAULTS,stagger_in=False))]:stack.enter_context(patch.object(runtime,name,return_value=value))
        stack.enter_context(patch.object(runtime.workspace_guard,'read',return_value={}))
        stack.enter_context(patch.object(runtime.workspace_guard,'ready',return_value=True))
        stack.enter_context(patch.object(runtime,'eww',side_effect=client))
        return state

    def test_edit_during_mapping_keeps_completed_widgets_and_retries_rest(self):
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            root=Path(td);widgets=[widget('old'),widget('new1'),widget('new2')]
            def changed(wid):
                if wid=='new1':(root/'conf').write_text('edited during open')
            state=self.harness(stack,root,widgets,{'old':runtime.spec(widgets[0])},changed)
            self.assertFalse(runtime.sync())
            self.assertEqual(state['active'],{'old','new1'})
            self.assertFalse(any(c[0]=='close' for c in state['commands']))
            self.assertEqual(set(json.loads((root/'applied').read_text())),{'old','new1'})
            self.assertTrue(runtime.sync());self.assertEqual(state['active'],{'old','new1','new2'})
            opened=[c[c.index('--id')+1] for c in state['commands'] if c[0]=='open']
            self.assertEqual(opened,['new1','new2'])

    def test_move_preserves_motion_and_does_not_prime_every_widget(self):
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            root=Path(td);old=widget('a');moved=copy.deepcopy(old);moved['x']=500
            state=self.harness(stack,root,[moved],{'a':runtime.spec(old)})
            with patch.object(runtime,'prime_data') as prime,patch.object(runtime,'set_motion') as motion:
                self.assertTrue(runtime.sync());prime.assert_not_called();motion.assert_not_called()
            self.assertEqual(state['active'],{'a'})
            self.assertFalse(any(c[0]=='close' for c in state['commands']))
            self.assertEqual(json.loads((root/'applied').read_text())['a'],runtime.spec(moved))

class WorkerSnapshotTests(unittest.TestCase):
    def test_snapshot_started_before_latest_edit_cannot_replace_its_geometry(self):
        from randly_widgets.editor_worker import EditorWorker
        entered=threading.Event();release=threading.Event();completed=threading.Event()
        def sample():
            entered.set();release.wait(2);return {'old_geometry':True}
        worker=EditorWorker('/tmp/example',sample,lambda _:completed.wait(2))
        try:
            self.assertTrue(entered.wait(2));worker.request(1);release.set()
            deadline=time.monotonic()+.1
            while time.monotonic()<deadline:
                with worker.lock:
                    if worker.snapshot is not None:break
                time.sleep(.001)
            snapshot,pending=worker.take()
            self.assertIsNone(snapshot);self.assertTrue(pending)
        finally:release.set();completed.set();worker.stop()
