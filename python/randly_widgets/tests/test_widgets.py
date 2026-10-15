import copy,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from randly_widgets import config
from randly_widgets.jobs import Scheduler
from randly_widgets.providers import load_provider,Context
from randly_widgets.registry import Registry,REGISTRY
from randly_widgets.composer import render,BuildError

def widget(wid='a',kind='api',**opts):return dict(id=wid,window=kind,show=True,anchor='top-left',x=0,y=0,opts=opts)

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.p1=patch.object(config,'CONF',str(self.root/'instances.json'));self.p2=patch.object(config,'LEGACY_CONF',str(self.root/'widgets.conf'))
        self.p1.start();self.p2.start();config._baseline=None
    def tearDown(self):self.p2.stop();self.p1.stop();self.temp.cleanup()
    def test_legacy_round_trip_and_idempotent_migration(self):
        text="gato cat on top-left 40 60 workspace=Todos\napi api on bottom-left 41 336 provider='Claude (Ambas)' label='cita con espacios'\n"
        Path(config.LEGACY_CONF).write_text(text)
        expected=config.parse_legacy(text);self.assertTrue(config.migrate());self.assertEqual(config.load(),expected)
        config.save(config.load());self.assertFalse(config.migrate());self.assertEqual(config.load(),expected)
    def test_three_way_preserves_other_instance_and_option(self):
        base=[widget('a',width='100'),widget('b')]
        desired=copy.deepcopy(base);desired[0]['opts']['width']='200'
        current=copy.deepcopy(base);current[0]['opts']['accent']='Primario';current[1]['x']=99;current.append(widget('c'))
        out=config.merge_widgets(base,desired,current)
        self.assertEqual(out[0]['opts'],{'width':'200','accent':'Primario'});self.assertEqual(out[1]['x'],99);self.assertEqual(out[2]['id'],'c')
    def test_conflict_is_explicit(self):
        base=[widget('a',width='100')];a=copy.deepcopy(base);b=copy.deepcopy(base);a[0]['opts']['width']='200';b[0]['opts']['width']='300'
        with self.assertRaises(config.Conflict):config.merge_widgets(base,a,b)
    def test_delete_and_add_have_no_sentinel_leak(self):
        base=[widget('a'),widget('b')];out=config.merge_widgets(base,[widget('a'),widget('c')],base)
        self.assertEqual([w['id'] for w in out],['a','c']);json.dumps(out)
    def test_cancel_reverts_own_fields_only(self):
        original=[widget('a',width='100')];last=copy.deepcopy(original);last[0]['x']=40
        config.save(last,base=[])
        current=config.load();current[0]['opts']['width']='200';config.save(current)
        config.rollback(original,last)
        self.assertEqual(config.load()[0]['x'],0);self.assertEqual(config.load()[0]['opts']['width'],'200')
    def test_bad_duplicate_config_does_not_replace_good(self):
        config.save([widget('a')],base=[]);before=Path(config.CONF).read_bytes()
        with self.assertRaises(config.ConfigError):config.save([widget('a'),widget('a')])
        self.assertEqual(Path(config.CONF).read_bytes(),before)

class ProviderTests(unittest.TestCase):
    def test_api_missing_file_never_creates_example_usage(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'absent.json';m=load_provider('api','fixture');ctx=Context(widget(),{'provider':'Lectura de archivo JSON','json_path':str(p)})
            data=m.collect(ctx);self.assertFalse(p.exists());self.assertEqual(data['pct_text'],'—')
    def test_api_instances_read_their_own_sources(self):
        with tempfile.TemporaryDirectory() as t:
            for name,pct in [('one',12),('two',67),('three',93)]:
                p=Path(t)/(name+'.json');p.write_text(json.dumps({'percent':pct,'label':name}))
                m=load_provider('api',name);ctx=Context(widget(name),{'provider':'Lectura de archivo JSON','json_path':str(p)})
                self.assertEqual(m.collect(ctx)['pct'],pct)
    def test_music_chooses_playing_and_exposes_exact_player(self):
        m=load_provider('music','music')
        def run(argv,**kwargs):
            if argv==['playerctl','-l']:return SimpleNamespace(stdout='paused.1\nplaying.2\n',returncode=0)
            return SimpleNamespace(stdout=('Playing' if argv[2]=='playing.2' else 'Paused')+'\x1fSong\x1fArtist',returncode=0)
        with patch.object(m.subprocess,'run',side_effect=run):
            self.assertEqual(m.collect(Context(widget('music','music'),{}))['player'],'playing.2')
    def test_countdown_and_note_are_removed_from_active_catalog(self):
        from randly_widgets.registry import SCHEMA
        self.assertNotIn('note',SCHEMA);self.assertNotIn('countdown',SCHEMA)

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.patch=patch('randly_widgets.jobs.RUNTIME',str(self.root));self.patch.start();self.schedulers=[]
    def tearDown(self):
        for s in self.schedulers:s.close()
        self.patch.stop();self.t.cleanup()
    def scheduler(self,source,execution='worker'):
        f=self.root/'provider.py';f.write_text(source)
        registry=SimpleNamespace(modules={'test':dict(path=str(self.root),provider='provider.py',execution=execution,interval=60,initial={})},missing={})
        s=Scheduler(registry,limit=2);self.schedulers.append(s);return s
    def test_inline_mutable_globals_are_per_instance(self):
        s=self.scheduler('counter=0\ndef collect(ctx):\n global counter\n counter+=1\n return {"counter":counter}\n','inline')
        ws=[widget('one','test'),widget('two','test')]
        out=s.tick(ws,lambda w:{},now=0);self.assertEqual(out['one']['counter'],1);self.assertEqual(out['two']['counter'],1)
    def test_bad_worker_does_not_block_healthy_widget(self):
        s=self.scheduler('def collect(ctx):\n if ctx.widget["id"]=="bad": raise ValueError("bad source")\n return {"value":42}\n')
        ws=[widget('bad','test'),widget('good','test')];s.tick(ws,lambda w:{})
        end=time.monotonic()+3
        while len(s.results)<2 and time.monotonic()<end:time.sleep(.02);s.tick(ws,lambda w:{})
        self.assertIn('error',s.results['bad']);self.assertEqual(s.results['good']['value'],42)
    def test_manual_mode_does_not_run_until_requested(self):
        marker=self.root/'ran'
        s=self.scheduler('from pathlib import Path\ndef collect(ctx):\n Path('+repr(str(marker))+').touch()\n return {"ok":True}\n')
        ws=[widget('manual','test')]
        s.tick(ws,lambda w:{'run':'Solo al hacer click'})
        self.assertFalse(s.jobs);self.assertFalse(marker.exists())
        (self.root/'eww-widgets-rerun-manual').touch();s.tick(ws,lambda w:{'run':'Solo al hacer click'})
        end=time.monotonic()+3
        while not marker.exists() and time.monotonic()<end:time.sleep(.02)
        self.assertTrue(marker.exists())
    def test_limits_and_cancel_on_hide(self):
        s=self.scheduler('import time\ndef collect(ctx):\n time.sleep(60)\n return {}\n')
        ws=[widget(str(i),'test') for i in range(5)];s.tick(ws,lambda w:{})
        self.assertEqual(len(s.jobs),2)
        ids=[p.pid for p,*_ in s.jobs.values()];s.tick([],lambda w:{})
        self.assertFalse(s.jobs)
        for pid in ids:
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
    def test_timeout_releases_slots(self):
        s=self.scheduler('import time\ndef collect(ctx):\n time.sleep(60)\n return {}\n')
        s.tick([widget('slow','test')],lambda w:{},now=1);s.collect_finished(22)
        self.assertFalse(s.jobs);self.assertIn('Tiempo agotado',s.results['slow']['error'])

class BuildTests(unittest.TestCase):
    def test_all_module_references_resolve_and_styles_are_scoped(self):
        yuck,css=render()
        definitions=set(__import__('re').findall(r'\(defwidget\s+([^\s\[()]+)',yuck))
        calls=set(__import__('re').findall(r'\((rw-[\w-]+)(?=[\s)])',yuck))
        self.assertFalse(calls-definitions,calls-definitions)
        self.assertNotIn('rw-wcfg',yuck);self.assertIn('https://github.com',yuck)
        self.assertNotIn('pkill',yuck)
    def test_two_profiles_have_different_namespaces_and_callbacks(self):
        one,_=render(config_dir='/tmp/profile-one');two,_=render(config_dir='/tmp/profile-two')
        self.assertNotEqual(one,two);self.assertIn('--config /tmp/profile-one',one);self.assertNotIn('--config /tmp/profile-two',one)
    def test_new_widget_requires_no_core_or_editor_change(self):
        from randly_widgets.cli import new_widget
        from randly_widgets.paths import EWW_DIR
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            import shutil
            shutil.copytree(Path(EWW_DIR)/'shared',root/'shared');shutil.copy2(Path(EWW_DIR)/'_colors.scss',root/'_colors.scss')
            new_widget('example',t)
            registry=Registry(t);self.assertIn('example',registry.schema())
            yuck,_=render(root,widgets=[widget('ex','example')],config_dir=root)
            self.assertIn('(defwindow rw-example',yuck)
    def test_activation_replacements_are_scoped_and_parse(self):
        import ast
        from randly_widgets.install import replacements
        for path,text in replacements().items():
            if path.suffix=='.py' or text.startswith('#!/usr/bin/env python3'):ast.parse(text)
            self.assertNotIn('pkill -9 -x eww',text)
        from randly_widgets.adapters.eww import argv
        self.assertIn('--config',argv('kill'))


class IsolationTests(unittest.TestCase):
    def test_daemon_discovery_ignores_other_profile(self):
        from randly_widgets.adapters.eww import owned_pids
        from randly_widgets.paths import EWW_DIR
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for pid,args in [('11',['eww','--config',EWW_DIR,'daemon']),('12',['eww','--config','/tmp/another-profile','daemon']),('13',['eww','daemon'])]:
                p=root/pid;p.mkdir();(p/'cmdline').write_bytes(b'\0'.join(x.encode() for x in args)+b'\0')
                (p/'stat').write_text(pid+' (eww) S '+'0 '*18+'101 '+'0 '*5)
            self.assertEqual(owned_pids(root),[(11,'101')])
    def test_unscoped_comma_selector_is_rejected(self):
        from randly_widgets.composer import check_styles
        with self.assertRaises(BuildError):check_styles('.rw-desktop.rw-cat .x, label { color: red; }','cat')
        check_styles('.rw-desktop.rw-cat .x { color: red; }','cat')
    def test_incomplete_css_rejected(self):
        from randly_widgets.composer import check_styles
        with self.assertRaises(BuildError):check_styles('.rw-desktop.rw-cat .x { color: red;','cat')
    def test_timers_are_independent_and_render_does_not_write_ticks(self):
        with tempfile.TemporaryDirectory() as t:
            one=load_provider('timer','one');two=load_provider('timer','two')
            one.STATE_DIR=two.STATE_DIR=Path(t)
            one.update('one',{},'timer-toggle');two.update('two',{},'timer-reset')
            self.assertTrue(one.get_timer_state('one')['running']);self.assertFalse(two.get_timer_state('two')['running'])
            path=Path(t)/'one/timer.json';before=path.read_bytes();one.collect(Context(widget('one','timer'),{}));self.assertEqual(path.read_bytes(),before)

    def test_failed_activation_restores_files_and_removes_new_instance_store(self):
        from randly_widgets import install
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'profile';root.mkdir()
            (root/'eww.yuck').write_text('old yuck')
            (root/'eww.scss').write_text('old style')
            generation=root/'generated/test';generation.mkdir(parents=True)
            (generation/'view.yuck').write_text('candidate')
            with patch.object(install,'EWW_DIR',str(root)),patch.object(install,'STATE_DIR',Path(t)/'state'):
                snapshot=install.activate_files(generation)
                self.assertTrue((root/'.modular-active').exists())
                (root/'instances.json').write_text('{}')
                install.restore_files(snapshot)
                self.assertEqual((root/'eww.yuck').read_text(),'old yuck')
                self.assertEqual((root/'eww.scss').read_text(),'old style')
                self.assertFalse((root/'.modular-active').exists())
                self.assertFalse((root/'instances.json').exists())
                self.assertFalse((root/'generated/current').exists())

    def test_json_access_requires_expression_braces(self):
        from randly_widgets.composer import check_forms
        with self.assertRaises(BuildError):
            check_forms('(revealer :reveal wcfg.g[wid].open)')
        check_forms('(revealer :reveal {wcfg.g[wid].open})')

    def test_all_catalog_views_have_no_bare_json_attribute(self):
        from randly_widgets.composer import check_forms
        for m in REGISTRY.modules.values():
            check_forms((Path(m['path'])/'view.yuck').read_text())

class GraphicValidationFlowTests(unittest.TestCase):
    def run_validation(self, explicit=False, broken=False, broken_css=False, no_confirmation=False, success_timeout=False, missing_window=False, other_error=False, delayed=False, wrong_kind=False, disappears=False):
        from randly_widgets import composer, paths
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);generation=root/'generation';generation.mkdir()
            (generation/'view.yuck').write_text('(deflisten wcfg :initial "{}" "unused cfg")\n(defwindow rw-cat [] (box))')
            (generation/'style.scss').write_text('')
            state={'stopped':False,'now':0.,'active':{},'queries':0};commands=[]
            process=SimpleNamespace(poll=lambda:0 if state['stopped'] else None,terminate=lambda:state.update(stopped=True),wait=lambda **kw:0)
            def popen(argv,**kw):
                state['log']=kw['stdout']
                state['style']=Path(argv[argv.index('--config')+1])/'eww.scss'
                if broken:
                    kw['stdout'].write('ERROR: parser rejected token\n');kw['stdout'].flush()
                return process
            def run(argv,**kw):
                commands.append(argv)
                self.assertNotIn('reload',argv,'El IPC reload de Eww vence a los 100ms')
                if 'open' in argv:
                    candidate=Path(argv[argv.index('--config')+1])/'eww.yuck'
                    self.assertNotIn('deflisten',candidate.read_text())
                    if not missing_window:state['active'][argv[argv.index('--id')+1]]='rw-api' if wrong_kind else argv[argv.index('open')+1]
                    if success_timeout:
                        state['log'].write(' 2026-10-15T06:41:17.938Z ERROR eww::error_handling_ctx > sending response from main thread\n\nCaused by:\n    0: Failed to send success response from application thread\n    1: channel closed\n')
                        state['log'].flush()
                    if other_error:
                        state['log'].write(' 2026-10-15T06:41:17.939Z ERROR eww::error_handling_ctx > Theme parsing error: invalid property\n');state['log'].flush()
                if 'active-windows' in argv:
                    state['queries']+=1
                    hidden=delayed and state['queries']<3 or disappears and state['now']>=.35
                    stdout='' if hidden else '\n'.join(wid+': '+kind for wid,kind in state['active'].items())
                else:stdout='' if broken else 'rw-cat\n'
                return SimpleNamespace(returncode=0,stdout=stdout,stderr='')
            def sleep(seconds):
                state["now"]+=seconds
                # Model the native watcher: only acknowledge after a real style
                # modification, never just because the daemon answered ping.
                modified='widgetctl validation' in state['style'].read_text()
                if modified and not no_confirmation:
                    state['log'].write('SCSS parsing error: expected selector\n' if broken_css else 'Reloaded config successfully\n')
                    state['log'].flush()
            ws=[widget('gato','cat')]
            with patch.object(composer,'graphics_available',return_value=(True,'')),patch.object(composer.subprocess,'Popen',side_effect=popen),patch.object(composer.subprocess,'run',side_effect=run),patch.object(composer.time,'sleep',side_effect=sleep),patch.object(composer.time,'monotonic',side_effect=lambda:state['now']),patch.object(composer,'load',return_value=ws) as loader,patch.object(paths,'STATE_DIR',root/'state'):
                if broken_css:
                    with self.assertRaisesRegex(BuildError,'SCSS parsing error'):
                        composer.validate_graphics(generation)
                    self.assertIn('SCSS parsing error',(root/'state/validation-last.log').read_text())
                elif missing_window or wrong_kind or disappears:
                    with self.assertRaisesRegex(BuildError,'no confirmó las ventanas'):
                        composer.validate_graphics(generation)
                    self.assertIn('verify-gato',(root/'state/validation-last.log').read_text())
                elif other_error:
                    with self.assertRaisesRegex(BuildError,'Theme parsing error'):
                        composer.validate_graphics(generation)
                elif no_confirmation:
                    with self.assertRaisesRegex(BuildError,'no confirmó'):
                        composer.validate_graphics(generation)
                    self.assertFalse(any('open' in a for a in commands))
                elif broken:
                    with self.assertRaisesRegex(BuildError,'parser rejected token'):
                        composer.validate_graphics(generation)
                    self.assertFalse(any('open' in a for a in commands))
                    self.assertIn('parser rejected token',(root/'state/validation-last.log').read_text())
                else:
                    self.assertTrue(composer.validate_graphics(generation,widgets=ws if explicit else None))
                    self.assertTrue(any('open' in a for a in commands))
                    self.assertEqual(loader.call_count,0 if explicit else 1)
    def test_expired_success_reply_passes_only_with_real_active_fixture(self):self.run_validation(success_timeout=True)
    def test_expired_success_reply_cannot_hide_missing_window(self):self.run_validation(success_timeout=True,missing_window=True)
    def test_real_gtk_error_is_kept_alongside_expired_success_reply(self):self.run_validation(success_timeout=True,other_error=True)
    def test_open_exit_zero_waits_for_late_mapping(self):self.run_validation(delayed=True)
    def test_matching_id_with_wrong_window_type_is_rejected(self):self.run_validation(wrong_kind=True)
    def test_window_that_disappears_after_open_is_rejected(self):self.run_validation(disappears=True)
    def test_reads_default_config_before_testing_windows(self):self.run_validation()
    def test_explicit_fixture_does_not_read_desktop_config(self):self.run_validation(explicit=True)
    def test_empty_window_list_reports_original_error(self):self.run_validation(broken=True)

    def test_scss_error_fails_validation_even_with_exit_zero(self):self.run_validation(broken_css=True)
    def test_sass_mixin_cannot_be_prefixed_as_a_selector(self):
        from randly_widgets.composer import check_shared_styles
        with self.assertRaises(BuildError):check_shared_styles('.rw-desktop @mixin accent($c, $on) {}')
        check_shared_styles('@mixin accent($c, $on) {}')

    def test_missing_css_confirmation_does_not_publish_unstyled_widgets(self):
        self.run_validation(no_confirmation=True)

class RuntimeReloadTests(unittest.TestCase):
    def test_restarts_only_profile_daemon_then_syncs(self):
        from randly_widgets import runtime
        with patch.object(runtime,'eww',return_value=None) as client,patch.object(runtime,'load_animation',return_value={}),patch.object(runtime,'restart_daemon',return_value=True) as restart,patch.object(runtime,'sync',return_value=True) as sync:
            self.assertTrue(runtime.reload())
            restart.assert_called_once_with();sync.assert_called_once_with(reloading=True)
            self.assertEqual(client.call_args_list,[unittest.mock.call('active-windows')])

    def test_failed_restart_does_not_sync(self):
        from randly_widgets import runtime
        with patch.object(runtime,'eww',return_value=None),patch.object(runtime,'load_animation',return_value={}),patch.object(runtime,'restart_daemon',return_value=False),patch.object(runtime,'sync') as sync:
            self.assertFalse(runtime.reload());sync.assert_not_called()

class LifecycleRegressionTests(unittest.TestCase):
    def test_rebuilding_same_generation_does_not_trigger_eww_filewatch(self):
        from randly_widgets import composer
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(composer,'render',return_value=('view','style')):
                folder=composer.build(Path(temp))
                before=[(folder/name).stat().st_mtime_ns for name in ('view.yuck','style.scss')]
                composer.build(Path(temp))
                self.assertEqual(before,[(folder/name).stat().st_mtime_ns for name in ('view.yuck','style.scss')])

    def test_add_existing_type_never_builds_or_reloads_desktop(self):
        from randly_widgets import api,composer
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);generation=root/'generated'/'one';generation.mkdir(parents=True)
            (generation/'view.yuck').write_text('(defwindow rw-cat [wid] (box))')
            (root/'generated/current').symlink_to('one')
            with patch.object(api,'EWW_DIR',temp),patch.object(composer,'build') as build,patch.object(api,'reload') as reload:
                self.assertTrue(api.ensure_current('cat'))
                build.assert_not_called();reload.assert_not_called()

    def test_custom_window_root_gets_native_transition_without_special_format(self):
        from randly_widgets.composer import wrap_window_roots,check_forms
        text='(defwidget rw-x [] (label :text "()"))\n(defwindow rw-x [wid] :geometry (geometry :width "0px") (eventbox (rw-x)))'
        wrapped=wrap_window_roots(text);check_forms(wrapped)
        self.assertIn('wcfg.m[wid]',wrapped);self.assertIn('wcfg.r[wid]',wrapped)
        self.assertIn('(eventbox (rw-x))',wrapped)
        self.assertEqual(wrapped.count('(revealer'),1)

    def test_catalog_has_no_css_in_out_animation(self):
        yuck,css=render()
        self.assertNotIn('@keyframes anim-',css)
        self.assertNotIn('animation: anim-',css)
        self.assertEqual(yuck.count('(defwindow '),yuck.count('(transform :class "rw-motion-space"'))

    def test_prime_new_widget_preserves_existing_data_and_waits_for_provider(self):
        from randly_widgets import runtime
        previous={'g':{'old':{'pct':71}},'r':{'old':True}}
        with patch.object(runtime,'eww',side_effect=[SimpleNamespace(returncode=0,stdout=json.dumps(previous)),SimpleNamespace(returncode=0)]) as client:
            self.assertTrue(runtime.prime_data([widget('old'),widget('new')]))
            payload=json.loads(client.call_args.args[2].split('=',1)[1])
            self.assertEqual(payload['g']['old']['pct'],71)
            self.assertTrue(payload['r']['old']);self.assertFalse(payload['r']['new'])
            self.assertIn('new',json.loads(client.call_args.args[1].split('=',1)[1]))

    def test_workspace_changes_mid_open_closes_that_window_before_reveal(self):
        from randly_widgets import runtime
        state={'valid':True}
        def client(*args):
            if args[0]=='open':state['valid']=False
            return SimpleNamespace(returncode=0,stdout='a: rw-api')
        with patch.object(runtime,'eww',side_effect=client) as eww,patch.object(runtime,'set_motion',return_value=True) as motion:
            self.assertFalse(runtime.eww_open_animated(['open','rw-api'],'a','fade',200,'fade',200,lambda:state['valid']))
            self.assertIn(unittest.mock.call('close','a'),eww.call_args_list)
            self.assertFalse(any(c.args[2] is True for c in motion.call_args_list))

    def test_failed_map_is_not_registered_and_later_valid_widget_still_opens(self):
        from randly_widgets import runtime
        anim=runtime.load_animation();by_id={w['id']:w for w in [widget('a'),widget('b')]}
        with patch.object(runtime,'eww_open_animated',side_effect=[False,True]):
            mapped=[]
            result=runtime.open_widgets(['a','b'],{'a':[],'b':[]},set(),by_id,anim,False,False,on_open=mapped.append)
            self.assertEqual(result,['b']);self.assertEqual(mapped,['b'])

    def test_stagger_cancels_remaining_windows_after_workspace_changes(self):
        from randly_widgets import runtime
        state={'valid':True};anim=runtime.load_animation()
        def first(*args):state['valid']=False;return True
        with patch.object(runtime,'eww_open_animated',side_effect=first) as opener,patch.object(runtime,'stagger_pause'):
            result=runtime.open_widgets(['a','b'],{'a':[],'b':[]},set(),{},anim,False,True,lambda:state['valid'])
            self.assertEqual(opener.call_count,1);self.assertEqual(result,['a'])

    def test_new_workspace_event_invalidates_previous_open_and_requires_settle(self):
        from randly_widgets import workspace_guard as gate
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'RUNTIME',temp):
            with patch.object(gate.time,'monotonic',return_value=10):
                first=gate.invalidate(.5);self.assertFalse(gate.ready(first['token']))
            with patch.object(gate.time,'monotonic',return_value=11):
                self.assertTrue(gate.ready(first['token']));second=gate.invalidate(.5)
                self.assertFalse(gate.ready(first['token']));self.assertFalse(gate.ready(second['token']))
            with patch.object(gate.time,'monotonic',return_value=12):self.assertTrue(gate.ready(second['token']))

    def test_partial_ipc_frames_are_reassembled(self):
        from randly_widgets.adapters.wayfire import wf_recv
        body=b'{"event":"wset-workspace-changed"}'
        parts=[__import__('struct').pack('<I',len(body))[:2],__import__('struct').pack('<I',len(body))[2:],body[:3],body[3:]]
        sock=SimpleNamespace(recv=lambda n:parts.pop(0))
        self.assertEqual(wf_recv(sock)['event'],'wset-workspace-changed')

    def test_missing_compositor_does_not_open_on_guessed_workspace_one(self):
        from randly_widgets import runtime
        with tempfile.TemporaryDirectory() as temp,patch.object(runtime,'LOCK',str(Path(temp)/'lock')),patch.object(runtime,'workspace_snapshot',return_value=None),patch.object(runtime,'is_disabled',return_value=False),patch.object(runtime,'eww') as eww:
            self.assertFalse(runtime.sync());eww.assert_not_called()

class WorkspaceReconciliationTests(unittest.TestCase):
    def test_fast_navigation_cancels_stale_open_preserves_global_and_opens_latest(self):
        from contextlib import ExitStack
        from randly_widgets import runtime
        widgets=[widget('global',workspace='Todos'),widget('first',workspace='Workspace 1'),widget('last',workspace='Workspace 2')]
        state={'place':(5,1,0,0,3),'active':{'global'},'switched':False};commands=[]
        def client(*args):
            commands.append(args)
            if args[0]=='active-windows':return SimpleNamespace(returncode=0,stdout='\n'.join(w+': rw-api' for w in state['active']))
            if args[0]=='open':
                wid=args[args.index('--id')+1];state['active'].add(wid)
                if wid=='first':state['place']=(5,1,1,0,3);state['switched']=True
            if args[0]=='close':state['active'].difference_update(args[1:])
            return SimpleNamespace(returncode=0,stdout='')
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);(root/'conf').touch()
            (root/'applied').write_text(json.dumps({'global':runtime.spec(widgets[0])}))
            for name,value in [('RUNTIME',temp),('LOCK',str(root/'lock')),('CONF',str(root/'conf')),('APPLIED',str(root/'applied'))]:stack.enter_context(patch.object(runtime,name,value))
            stack.enter_context(patch.object(runtime,'workspace_snapshot',side_effect=lambda:state['place']))
            stack.enter_context(patch.object(runtime,'is_disabled',return_value=False))
            stack.enter_context(patch.object(runtime,'power_policy',return_value={}))
            stack.enter_context(patch.object(runtime,'load',return_value=widgets))
            stack.enter_context(patch.object(runtime,'prime_data',return_value=True))
            stack.enter_context(patch.object(runtime,'set_motion',return_value=True))
            stack.enter_context(patch.object(runtime,'wf_view_ids',return_value={}))
            stack.enter_context(patch.object(runtime.workspace_guard,'read',return_value={}))
            stack.enter_context(patch.object(runtime.workspace_guard,'ready',return_value=True))
            stack.enter_context(patch.object(runtime,'load_animation',return_value=dict(runtime.ANIM_DEFAULTS,stagger_in=False)))
            stack.enter_context(patch.object(runtime,'eww',side_effect=client))
            self.assertTrue(runtime.sync());self.assertTrue(state['switched'])
            self.assertEqual(state['active'],{'global'})
            self.assertEqual(set(json.loads((root/'applied').read_text())),{'global'})
            self.assertTrue(runtime.sync())
            self.assertEqual(state['active'],{'global','last'})
            self.assertEqual(set(json.loads((root/'applied').read_text())),{'global','last'})
            self.assertFalse(any(args[0]=='close' and 'global' in args[1:] for args in commands))

class NativeMotionTests(unittest.TestCase):
    def test_inherited_and_explicit_effects_follow_user_settings(self):
        from randly_widgets.runtime import widget_effects,load_animation
        anim=dict(load_animation(),anim_in='slideleft',anim_out='fade')
        self.assertEqual(widget_effects(widget(anim='global',anim_out='global'),anim),('slideleft','fade'))
        self.assertEqual(widget_effects(widget(anim='slideup',anim_out='none'),anim),('slideup','none'))

    def test_changing_one_widget_keeps_other_revealed(self):
        from randly_widgets import transitions
        client=lambda *args:SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as temp,patch.object(transitions,'RUNTIME',temp):
            self.assertTrue(transitions.set_motion(client,['a'],True,'fade',200))
            self.assertTrue(transitions.set_motion(client,['b'],False,'slide',300))
            data=json.loads((Path(temp)/'motion.json').read_text())
            self.assertTrue(data['a']['reveal']);self.assertFalse(data['b']['reveal'])
            self.assertEqual(data['b']['transition'],'crossfade');self.assertEqual(data['b']['effect'],'slide')

    def test_out_finishes_before_window_is_destroyed(self):
        from randly_widgets import runtime
        clock={'now':0};closed=[]
        def sleep(seconds):clock['now']+=seconds
        def client(*args):
            if args[0]=='close':closed.append(clock['now'])
            return SimpleNamespace(returncode=0)
        anim=dict(runtime.ANIM_DEFAULTS,anim_out='fade',duration_out=200)
        with patch.object(runtime,'eww',side_effect=client),patch.object(runtime,'set_motion',return_value=True) as motion,patch.object(runtime,'wf_view_ids',return_value={}),patch.object(runtime.time,'monotonic',side_effect=lambda:clock['now']),patch.object(runtime.time,'sleep',side_effect=sleep):
            runtime.close_widgets(['a'],{},anim,True,False)
            self.assertGreaterEqual(closed[0],.2)
            self.assertFalse(motion.call_args.args[2])

    def test_workspace_close_does_not_wait_for_out(self):
        from randly_widgets import runtime
        with patch.object(runtime,'eww'),patch.object(runtime,'set_motion',return_value=True) as motion,patch.object(runtime,'wf_view_ids',return_value={}),patch.object(runtime.time,'sleep') as sleep:
            runtime.close_widgets(['a'],{},runtime.load_animation(),False,False)
            sleep.assert_not_called();self.assertEqual(motion.call_args.args[3:5],('none',0))

    def test_watcher_discovery_cannot_stop_other_eww_projects(self):
        from randly_widgets.watcher import owned_watchers
        from randly_widgets.paths import EWW_DIR
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ctl=str(Path.home()/'.local/bin/widgetctl')
            cases=[('11',['python3',ctl,'--config',EWW_DIR,'watch']),('12',['python3',ctl,'--config','/tmp/another-profile','watch']),('13',['python3',ctl,'--config',EWW_DIR,'cfg'])]
            for pid,args in cases:
                p=root/pid;p.mkdir();(p/'cmdline').write_bytes(b'\0'.join(x.encode() for x in args)+b'\0')
                (p/'stat').write_text(pid+' (python3) S '+'0 '*18+'101 '+'0 '*5)
            self.assertEqual(owned_watchers(root),[(11,'101')])

class ExtendedMotionTests(unittest.TestCase):
    def test_idle_pose_is_literal_identity_for_every_effect(self):
        from randly_widgets.transitions import KEYS,pose
        for effect in KEYS:
            self.assertEqual(pose(effect,1),{'sx':'100%','sy':'100%','x':'0%','y':'0%','rotate':0.0})

    def test_window_motion_uses_one_transform_without_translated_parent_clip(self):
        from randly_widgets.composer import wrap_window_roots,check_forms
        wrapped=wrap_window_roots('(defwindow rw-x [wid] (box (label :text "full width")))')
        check_forms(wrapped)
        self.assertEqual(wrapped.count('(transform '),1)
        self.assertNotIn('wcfg.m[wid]?.cx',wrapped)
        self.assertNotIn('wcfg.m[wid]?.cy',wrapped)
        self.assertNotIn('?: "50%"',wrapped)
        yuck,_=render()
        self.assertEqual(yuck.count('(transform :class "rw-motion-space"'),yuck.count('(defwindow '))

    def test_reopen_uses_new_phase_token_so_queued_old_frames_cannot_flash(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();data={'a':{}};ready={'a':True};opts={'a':{'motion_mode':'staged'}}
        first={'a':{'token':'old','reveal':True,'effect':'zoom','ms':300}}
        engine.step(first,data,ready,opts,0)
        old,_,_=engine.step(first,data,ready,opts,.5)
        self.assertTrue(old['a']['show'])
        second={'a':{'token':'new','reveal':True,'effect':'vortex','ms':400}}
        self.assertNotEqual(second['a']['token'],old['a']['token'])
        new,_,_=engine.step(second,data,ready,opts,.6)
        self.assertEqual(new['a']['token'],'new');self.assertNotEqual(new['a']['sx'],'100%')
        yuck,_=render();self.assertIn('wmotion[wid]?.token == wframes[wid]?.token',yuck)

    def test_requested_effects_have_distinct_native_geometry_and_exact_final_pose(self):
        from randly_widgets.transitions import pose
        effects=['zoom','pop','vortex','zap','glitch','spin']
        signatures={json.dumps(pose(key,.35),sort_keys=True) for key in effects}
        self.assertEqual(len(signatures),len(effects))
        for key in effects:
            self.assertEqual(pose(key,1),pose('none',1))
            for p in (0,.2,.5,.9,1):
                frame=pose(key,p)
                self.assertGreaterEqual(float(frame['sx'].strip('%')),0)
                self.assertGreaterEqual(float(frame['sy'].strip('%')),0)

    def test_stable_mode_waits_for_ready_data_then_stability(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={'a':{'token':'one','reveal':True,'effect':'zoom','ms':400}}
        frame,_,_=engine.step(request,{'a':{'text':'pending'}},{'a':False},{},0)
        self.assertFalse(frame['a']['show'])
        frame,_,_=engine.step(request,{'a':{'text':'loaded'}},{'a':True},{},10)
        self.assertFalse(frame['a']['show'])
        frame,_,_=engine.step(request,{'a':{'text':'loaded'}},{'a':True},{},10.2)
        self.assertTrue(frame['a']['show']);self.assertNotEqual(frame['a']['sx'],'100%')

    def test_data_changing_forever_cannot_delay_entry_forever(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={'a':{'token':'one','reveal':True,'effect':'pop','ms':300}}
        for n in range(12):frame,_,_=engine.step(request,{'a':{'count':n}},{'a':True},{},n*.1)
        self.assertTrue(frame['a']['show'])

    def test_entry_freezes_content_until_motion_finishes(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={'a':{'token':'one','reveal':True,'effect':'zoom','ms':500}}
        opts={'a':{'motion_mode':'staged'}}
        engine.step(request,{'a':{'text':'first'}},{'a':True},opts,0)
        _,data,_=engine.step(request,{'a':{'text':'new size'}},{'a':True},opts,.2)
        self.assertEqual(data['a']['text'],'first')
        _,data,running=engine.step(request,{'a':{'text':'new size'}},{'a':True},opts,.6)
        self.assertEqual(data['a']['text'],'new size');self.assertFalse(running)

    def test_staged_mode_has_fade_phase_before_expansion(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={'a':{'token':'one','reveal':True,'effect':'zoom','ms':600}}
        opts={'a':{'motion_mode':'staged'}};data={'a':{}};ready={'a':True}
        first,_,_=engine.step(request,data,ready,opts,0)
        middle,_,_=engine.step(request,data,ready,opts,.1)
        late,_,_=engine.step(request,data,ready,opts,.4)
        self.assertEqual(first['a']['sx'],middle['a']['sx'])
        self.assertNotEqual(middle['a']['sx'],late['a']['sx'])
        self.assertEqual(first['a']['fade_duration'],'180ms')

    def test_new_request_cancels_old_geometry_without_revealing_it_later(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();opts={'a':{'motion_mode':'staged'}};data={'a':{}};ready={'a':True}
        engine.step({'a':{'token':'one','reveal':True,'effect':'vortex','ms':600}},data,ready,opts,0)
        frame,_,running=engine.step({'a':{'token':'two','reveal':False,'effect':'none','ms':0}},data,ready,opts,.1)
        self.assertFalse(frame['a']['show']);self.assertFalse(running)

    def test_settling_one_widget_does_not_block_another(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={key:{'token':key,'reveal':True,'effect':'zoom','ms':300} for key in ('a','b')}
        frame,_,_=engine.step(request,{'a':{},'b':{}},{'a':False,'b':True},{'b':{'motion_mode':'staged'}},0)
        self.assertFalse(frame['a']['show']);self.assertTrue(frame['b']['show'])

    def test_none_and_power_reduced_requests_finish_without_frame_loop(self):
        from randly_widgets.transitions import MotionEngine
        engine=MotionEngine();request={'a':{'token':'one','reveal':True,'effect':'none','ms':300}}
        frame,_,running=engine.step(request,{'a':{}},{'a':True},{},0)
        self.assertTrue(frame['a']['show']);self.assertFalse(running);self.assertEqual(frame['a']['sx'],'100%')

    def test_prime_data_never_hides_existing_widgets_when_adding(self):
        from randly_widgets import runtime
        previous={'g':{'old':{'pct':71}},'r':{'old':True},'m':{'old':{'show':True,'sx':'100%'}}}
        with patch.object(runtime,'eww',side_effect=[SimpleNamespace(returncode=0,stdout=json.dumps(previous)),SimpleNamespace(returncode=0)]) as client:
            self.assertTrue(runtime.prime_data([widget('old'),widget('new')]))
            payload=json.loads(client.call_args.args[1].split('=',1)[1])
            self.assertEqual(payload['m']['old'],previous['m']['old'])
            self.assertTrue(payload['r']['old'])
            self.assertFalse(any(arg.startswith('wframes=') for arg in client.call_args.args))

class PaletteStyleTests(unittest.TestCase):
    def test_every_requested_profile_and_background_resolves_with_palette_class(self):
        from randly_widgets.appearance import options
        from randly_widgets.themes import BACKGROUNDS
        for skin in ('monochrome','retro','zsh','gnome','terminal'):
            for background in BACKGROUNDS:
                result=options(widget(skin=skin,background=background))
                self.assertIn('skin-'+skin,result['skin_class']);self.assertIn('bg-'+background,result['skin_class'])

    def test_all_juice_choices_resolve_and_power_policy_disables_them(self):
        from randly_widgets import appearance
        from randly_widgets.themes import FX
        with patch.object(appearance,'power_policy',return_value={'ambient_effects':True}):
            for key in FX:self.assertEqual(appearance.options(widget(fx=key))['fx'],key)
        with patch.object(appearance,'power_policy',return_value={'ambient_effects':False}):
            self.assertEqual(appearance.options(widget(fx='prism'))['fx_class'],'')

    def test_pulse_is_transparent_after_all_background_rules(self):
        _,css=render()
        self.assertGreater(css.index('.rw-desktop.wroot.fx-pulse {',css.index('// shared effects.scss')),css.index('.rw-desktop.wroot.bg-primary'))
        effects=css[css.index('// shared effects.scss'):]
        self.assertIn('@include rw-surfaces { background-color: transparent; }',effects)
        self.assertNotIn('background-color:',effects[:effects.index('// Breathing')])

    def test_new_style_files_use_palette_roles_and_gtk_keyframe_syntax(self):
        from randly_widgets.paths import EWW_DIR
        for name in ('themes.scss','effects.scss'):
            text=(Path(EWW_DIR)/'shared'/name).read_text()
            self.assertNotRegex(text,r'#[0-9a-fA-F]{3,8}\b')
            self.assertNotRegex(text,r'\d+%,\s*\d+%')
        yuck,_=render();self.assertNotIn('transform-origin-x',yuck)

class SuccessReplyFilteringTests(unittest.TestCase):
    def test_generic_and_failed_response_channel_errors_are_never_suppressed(self):
        from randly_widgets.composer import without_confirmed_success_timeouts,css_failure
        for message in ('sending response from main thread\n\nCaused by:\n    0: Failed to send failure response from application thread\n    1: channel closed\n','generic channel closed\n'):
            logs=' 2026-10-15T06:41:17.938Z ERROR eww::error_handling_ctx > '+message
            self.assertEqual(without_confirmed_success_timeouts(logs),logs)
            self.assertTrue(css_failure(logs))

    def test_removing_success_timeout_preserves_next_css_diagnostic(self):
        from randly_widgets.composer import without_confirmed_success_timeouts
        harmless=' 2026-10-15T06:41:17.938Z ERROR eww::error_handling_ctx > Failed to send success response from application thread\n\nCaused by:\n    channel closed\n'
        real=' 2026-10-15T06:41:17.939Z ERROR eww::error_handling_ctx > SCSS parsing error: invalid token\n'
        self.assertEqual(without_confirmed_success_timeouts(harmless+real),real)

if __name__=='__main__':unittest.main()
