"""Native controller integration with a test-only IPC transport and an isolated fake Eww."""
import hashlib,json,os,select,socket,struct,subprocess,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ.get('WIDGET_MANAGER_TEST_BIN',str(ROOT/'target/debug/randly-widget-manager')))
FAKE=r'''#!/usr/bin/python3
import json,os,sys,time
from pathlib import Path
args=sys.argv[4:];path=Path(os.environ['FAKE_EWW_STATE']);s=json.loads(path.read_text());s['commands'].append(args)
cmd=args[0];output=''
if cmd=='active-windows':output='\n'.join(k+': '+v for k,v in s['active'].items()) if not os.environ.get('FAKE_EMPTY_ACTIVE') else ''
elif cmd=='open':
 wid=args[args.index('--id')+1];s['active'][wid]=args[1]
 if os.environ.get('FAKE_SWITCH_ON_OPEN')==wid:Path(os.environ['FAKE_SWITCH']).touch()
 if os.environ.get('FAKE_EDIT_ON_OPEN')==wid:
  conf=Path(sys.argv[2])/'instances.json';v=json.loads(conf.read_text());v['revision']+=1;v['widgets'][0]['opts']['changed']='yes';conf.write_text(json.dumps(v))
elif cmd=='close':
 for wid in args[1:]:s['active'].pop(wid,None)
elif cmd=='kill':s['active']={}
elif cmd=='update':
 for arg in args[1:]:
  k,_,v=arg.partition('=');s[k]=json.loads(v)
 if os.environ.get('FAKE_SWITCH_ON_OUT') and any(not v.get('reveal') and v.get('effect') not in (None,'none') for v in s.get('wmotion',{}).values()):Path(os.environ['FAKE_SWITCH']).touch()
if os.environ.get('FAKE_TIMELINE'):
 entry={'time':time.monotonic(),'args':args}
 css=Path(os.environ.get('FAKE_CSS','/absent'))
 if css.is_file():entry['css']=css.read_text()
 with open(os.environ['FAKE_TIMELINE'],'a') as f:f.write(json.dumps(entry)+'\n')
path.write_text(json.dumps(s));print(output)
'''
def widget(wid='a',workspace='Global',x=400,y=500):return dict(id=wid,window='api',show=True,anchor='bottom-right',x=x,y=y,opts={'workspace':workspace})

class NativeManagerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.config=self.root/'profile';self.config.mkdir()
  self.state_path=self.root/'fake.json';self.state_path.write_text(json.dumps({'active':{},'commands':[]}))
  self.eww=self.root/'eww';self.eww.write_text(FAKE);self.eww.chmod(0o755)
  self.switch=self.root/'switch';self.socket_path=self.root/'wf.sock'
  self.fixture=self.root/'ipc-fixture.json';self.fixture.write_text(json.dumps({'state':str(self.state_path),'switch':str(self.switch)}))
  key=hashlib.sha256(str(self.config).encode()).hexdigest()[:12];self.prefix='rw-'+key+'-';self.runtime=self.root/'run/randly-widgets'/key
  (self.config/'.modular-active').touch();(self.config/'widgets/api').mkdir(parents=True);(self.config/'widgets/api/manifest.json').write_text('{"id":"api","enabled":true}')
  (self.config/'generated/current').mkdir(parents=True)
  (self.config/'generated/current/view.yuck').write_text('(defwindow rw-api [wid] (box))')
  (self.config/'generated/current/style.scss').write_text('$primary:#000000;\n// RW_PALETTE_END\n.rw-desktop {color:$primary;}\n')
  (self.config/'_colors.scss').write_text('$primary:#112233;\n')
  self.env={**os.environ,'XDG_RUNTIME_DIR':str(self.root/'run'),'XDG_STATE_HOME':str(self.root/'state'),'WAYFIRE_SOCKET':str(self.socket_path),'RANDLY_EWW_BIN':str(self.eww),'FAKE_EWW_STATE':str(self.state_path),'FAKE_SWITCH':str(self.switch),'RANDLY_WIDGETS_TEST_WF':str(self.fixture)}
  self.configure([widget()])
 def configure(self,widgets):self.widgets=widgets;(self.config/'instances.json').write_text(json.dumps(dict(version=1,revision=1,widgets=widgets)))
 def state(self):return json.loads(self.state_path.read_text())
 def invoke(self,*args,**env):return subprocess.run([str(BIN),'--config',str(self.config),*args],env={**self.env,**env},capture_output=True,text=True,timeout=15)
 def tearDown(self):self.tmp.cleanup()
 def test_native_opens_at_saved_position_without_python_manager(self):
  r=self.invoke('sync');self.assertEqual(r.returncode,0,r.stderr)
  state=self.state();self.assertEqual(state['active'],{'a':'rw-api'})
  opens=[c for c in state['commands'] if c[0]=='open'];self.assertEqual(len(opens),1)
  self.assertEqual(opens[0][opens[0].index('--pos')+1],'400x500')
  self.assertEqual(opens[0][opens[0].index('--anchor')+1],'bottom right')
  applied_stamp=(self.runtime/'eww-widgets-applied.json').stat().st_mtime_ns
  before=len(state['commands']);self.assertEqual(self.invoke('sync').returncode,0)
  self.assertEqual((self.runtime/'eww-widgets-applied.json').stat().st_mtime_ns,applied_stamp)
  self.assertFalse(any(c[0] in ('open','close') for c in self.state()['commands'][before:]))
 def test_editor_global_filter_is_exclusive(self):
  self.configure([widget('global'),widget('local','Workspace 1')]);self.assertEqual(self.invoke('sync').returncode,0)
  (self.runtime/'eww-widgets-editing').write_text('global')
  r=self.invoke('sync','global');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.state()['active'],{'global':'rw-api'})
 def test_workspace_switch_cancels_only_obsolete_open(self):
  self.configure([widget('global'),widget('first','Workspace 1'),widget('last','Workspace 2')])
  r=self.invoke('sync',FAKE_SWITCH_ON_OPEN='first');self.assertEqual(r.returncode,1,r.stderr)
  self.assertEqual(self.state()['active'],{'global':'rw-api'})
  self.assertEqual(self.invoke('sync').returncode,0);self.assertEqual(set(self.state()['active']),{'global','last'})
  self.assertFalse(any(c[0]=='close' and 'global' in c[1:] for c in self.state()['commands']))
 def test_config_edit_preserves_already_completed_open(self):
  self.configure([widget('first'),widget('second')]);self.assertEqual(self.invoke('sync',FAKE_EDIT_ON_OPEN='first').returncode,1)
  self.assertEqual(self.state()['active'],{'first':'rw-api'});self.assertEqual(self.invoke('sync').returncode,0)
  self.assertEqual([c[c.index('--id')+1] for c in self.state()['commands'] if c[0]=='open'],['first','second'])
 def test_empty_ipc_reply_uses_surfaces_without_reopening(self):
  self.assertEqual(self.invoke('sync').returncode,0);before=len(self.state()['commands'])
  r=self.invoke('sync',FAKE_EMPTY_ACTIVE='1');self.assertEqual(r.returncode,0,r.stderr)
  self.assertFalse(any(c[0] in ('open','close') for c in self.state()['commands'][before:]))
 def test_theme_only_changes_external_css_never_windows_or_generation(self):
  (self.config/'animation.json').write_text('{"palette_animation":false}')
  self.assertEqual(self.invoke('sync').returncode,0);before=self.state();applied=(self.runtime/'eww-widgets-applied.json').read_bytes();source=self.config/'generated/current/style.scss';stamp=source.stat().st_mtime_ns
  result=self.invoke('theme');self.assertEqual(result.returncode,0,result.stderr)
  css=(self.runtime/'theme.css').read_text();self.assertIn('#112233',css)
  (self.config/'_colors.scss').write_text('$primary:#445566;\n');self.assertEqual(self.invoke('theme').returncode,0)
  self.assertIn('#445566',(self.runtime/'theme.css').read_text());self.assertEqual(self.state(),before)
  self.assertEqual((self.runtime/'eww-widgets-applied.json').read_bytes(),applied);self.assertEqual(source.stat().st_mtime_ns,stamp)
 def test_invalid_palette_keeps_last_valid_css(self):
  r=self.invoke('theme');self.assertEqual(r.returncode,0,r.stderr);old=(self.runtime/'theme.css').read_bytes()
  before=self.state()
  (self.config/'_colors.scss').write_text('$primary: invalidcolor;\n');self.assertNotEqual(self.invoke('theme').returncode,0)
  self.assertEqual((self.runtime/'theme.css').read_bytes(),old);self.assertEqual(self.state(),before)
 def animation(self,**values):
  settings={'when':'workspace','anim_in':'zoom','anim_out':'fade','duration_in':120,'duration_out':60,'delay_in':80,'max_parallel':3,'fps':24,'stagger_in':False,'stagger_out':False,**values}
  (self.config/'animation.json').write_text(json.dumps(settings));return settings
 def test_batch_mapping_and_bounded_concurrency_for_twenty_widgets(self):
  self.configure([widget('a'+str(i)) for i in range(20)]);self.animation()
  r=self.invoke('sync');self.assertEqual(r.returncode,0,r.stderr)
  commands=self.state()['commands'];self.assertLessEqual(sum(c[0]=='active-windows' for c in commands),3)
  self.assertEqual(sum(c[0]=='update' for c in commands),2)
  controls=self.state()['wmotion'];events=[]
  for motion in controls.values():
   self.assertTrue(motion['reveal']);self.assertEqual(motion['effect'],'zoom');self.assertGreaterEqual(motion['delay_ms'],80)
   events.extend([(motion['delay_ms'],1),(motion['delay_ms']+motion['ms'],-1)])
  current=peak=0
  for _,delta in sorted(events):current+=delta;peak=max(peak,current)
  self.assertEqual(peak,3)
 def test_normal_workspace_exit_waits_for_out_before_close(self):
  self.configure([widget('global'),widget('local','Workspace 1')]);self.animation()
  self.assertEqual(self.invoke('sync').returncode,0);self.switch.touch();timeline=self.root/'timing.jsonl'
  r=self.invoke('sync',FAKE_TIMELINE=str(timeline));self.assertEqual(r.returncode,0,r.stderr)
  records=[json.loads(line) for line in timeline.read_text().splitlines()]
  out=next(e for e in records if e['args'][0]=='update' and json.loads(e['args'][1].split('=',1)[1])['local']['effect']=='fade')
  closed=next(e for e in records if e['args'][0]=='close')
  self.assertGreaterEqual(closed['time']-out['time'],.12);self.assertEqual(self.state()['active'],{'global':'rw-api'})
 def test_canceled_exit_recovers_when_returning_to_workspace(self):
  self.configure([widget('global'),widget('first','Workspace 1'),widget('last','Workspace 2')]);self.animation()
  self.assertEqual(self.invoke('sync').returncode,0)
  r=self.invoke('sync','2',FAKE_SWITCH_ON_OUT='1');self.assertEqual(r.returncode,1,r.stderr)
  self.switch.unlink();self.assertEqual(self.invoke('sync').returncode,0)
  self.assertTrue(self.state()['wmotion']['first']['reveal']);self.assertEqual(set(self.state()['active']),{'global','first'})
 def test_palette_out_changes_css_then_in_without_remapping(self):
  self.animation(palette_animation=False);self.assertEqual(self.invoke('theme').returncode,0)
  self.assertEqual(self.invoke('sync').returncode,0);before=len(self.state()['commands']);self.animation()
  (self.config/'_colors.scss').write_text('$primary:#abcdef;\n');timeline=self.root/'palette.jsonl'
  r=self.invoke('theme',FAKE_TIMELINE=str(timeline),FAKE_CSS=str(self.runtime/'theme.css'));self.assertEqual(r.returncode,0,r.stderr)
  commands=self.state()['commands'][before:];self.assertFalse(any(c[0] in ('open','close','kill','reload') for c in commands))
  records=[json.loads(line) for line in timeline.read_text().splitlines() if json.loads(line)['args'][0]=='update']
  self.assertEqual(len(records),2)
  self.assertFalse(json.loads(records[0]['args'][1].split('=',1)[1])['a']['reveal']);self.assertIn('#112233',records[0]['css'])
  self.assertTrue(json.loads(records[1]['args'][1].split('=',1)[1])['a']['reveal']);self.assertIn('#abcdef',records[1]['css'])
 def test_palette_cancellation_restores_global_on_new_workspace(self):
  self.configure([widget('global'),widget('local','Workspace 1')]);self.animation(palette_animation=False)
  self.assertEqual(self.invoke('theme').returncode,0);self.assertEqual(self.invoke('sync').returncode,0);self.animation()
  (self.config/'_colors.scss').write_text('$primary:#abcdef;\n')
  r=self.invoke('theme',FAKE_SWITCH_ON_OUT='1');self.assertEqual(r.returncode,0,r.stderr)
  self.assertTrue(self.state()['wmotion']['global']['reveal']);self.assertFalse(self.state()['wmotion']['local']['reveal'])
  self.assertIn('#abcdef',(self.runtime/'theme.css').read_text())
 def test_native_edits_preserve_other_widgets_and_custom_metadata(self):
  a=widget('a');a['custom']={'keep':True};b=widget('b');self.configure([a,b])
  r=self.invoke('set','a','x=123','width=320');self.assertEqual(r.returncode,0,r.stderr)
  value=json.loads((self.config/'instances.json').read_text());self.assertEqual(value['widgets'][0]['x'],123)
  self.assertEqual(value['widgets'][0]['custom'],{'keep':True});self.assertEqual(value['widgets'][1],b)
  self.assertEqual(self.invoke('duplicate','a').returncode,0)
  self.assertEqual(self.invoke('disable','a').returncode,0)
  saved=json.loads((self.config/'instances.json').read_text())['widgets'];self.assertFalse(saved[0]['show']);self.assertEqual(saved[-1]['id'],'a2')
  self.assertEqual(self.invoke('remove','a2').returncode,0)
  self.assertEqual(self.invoke('add','api','--id','new').returncode,0)
  saved=json.loads((self.config/'instances.json').read_text())['widgets'];self.assertEqual(saved[-1]['id'],'new')
 def test_invalid_native_edit_never_replaces_configuration(self):
  before=(self.config/'instances.json').read_bytes()
  self.assertNotEqual(self.invoke('set','a','anchor=not-valid').returncode,0)
  self.assertEqual((self.config/'instances.json').read_bytes(),before)
 def test_css_bridge_only_initializes_in_eww_and_does_not_leak_preload(self):
  source=self.root/'probe.rs';source.write_text('fn main(){println!("{}",std::env::var("LD_PRELOAD").unwrap_or_default());}')
  directory=self.root/'probe';directory.mkdir();probe=directory/'eww'
  result=subprocess.run(['rustc',str(source),'-o',str(probe)],capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stderr)
  env={**self.env,'LD_PRELOAD':str(ROOT/'target/release/librandly_widget_theme.so'),'RANDLY_WIDGETS_THEME_CSS':str(self.root/'theme.css')}
  result=subprocess.run([str(probe)],env=env,capture_output=True,text=True,timeout=3)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'')
 def test_live_theme_preserves_widget_local_resize_priority(self):
  # Run the actual bridge callback with a screen spy, without a compositor.
  # GTK gives widget-local :style precedence at equal APPLICATION priority.
  mock=self.root/'screen.c'
  mock.write_text('#include <stdio.h>\nvoid *gdk_screen_get_default(void){return (void*)1;}\nvoid gtk_style_context_add_provider_for_screen(void *s,void *p,unsigned priority){printf("%u\\n",priority);fflush(stdout);}\n')
  shim=self.root/'screen.so'
  result=subprocess.run(['cc','-shared','-fPIC',str(mock),'-o',str(shim)],capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stderr)
  source=self.root/'callback.rs'
  source.write_text('extern "C" {fn g_main_context_iteration(c:*mut std::ffi::c_void, wait:i32)->i32;} fn main(){for _ in 0..4{std::thread::sleep(std::time::Duration::from_millis(60)); unsafe {g_main_context_iteration(std::ptr::null_mut(),0);}}}')
  directory=self.root/'callback';directory.mkdir();probe=directory/'eww'
  result=subprocess.run(['rustc',str(source),'-l','glib-2.0','-o',str(probe)],capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stderr)
  css=self.root/'resize.css';css.write_text('.rw-desktop * {all:unset;}')
  env={**self.env,'LD_PRELOAD':str(shim)+' '+str(ROOT/'target/release/librandly_widget_theme.so'),'RANDLY_WIDGETS_THEME_CSS':str(css)}
  result=subprocess.run([str(probe)],env=env,capture_output=True,text=True,timeout=3)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertTrue(result.stdout.strip(),result.stderr)
  self.assertLessEqual(int(result.stdout.strip()),600,'Global palette CSS must not override Eww inline min-width/height')
 def test_native_frames_use_existing_protocol_and_stop_on_signal(self):
  self.runtime.mkdir(parents=True,exist_ok=True)
  (self.runtime/'data-snapshot.json').write_text(json.dumps({'g':{'a':{'text':'ready'}},'r':{'a':True},'o':{}}))
  (self.runtime/'motion.json').write_text(json.dumps({'a':{'token':'current','reveal':True,'effect':'none','ms':0}}))
  p=subprocess.Popen([str(BIN),'--config',str(self.config),'frames'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   self.assertTrue(select.select([p.stdout],[],[],3)[0]);value=json.loads(p.stdout.readline())
   self.assertTrue(value['a']['show']);self.assertEqual(value['a']['token'],'current');self.assertEqual(value['a']['sx'],'100%')
  finally:
   p.terminate();p.wait(timeout=2);p.stdout.close();p.stderr.close()
 def test_frames_only_keep_visible_widgets_in_memory(self):
  self.runtime.mkdir(parents=True,exist_ok=True)
  values={str(i):{} for i in range(100)}
  (self.runtime/'data-snapshot.json').write_text(json.dumps({'g':values,'r':{i:True for i in values},'o':{}}))
  (self.runtime/'eww-widgets-applied.json').write_text('{"1":[]}')
  (self.runtime/'motion.json').write_text(json.dumps({i:{'token':i,'reveal':True,'effect':'none','ms':0} for i in values}))
  p=subprocess.Popen([str(BIN),'--config',str(self.config),'frames'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   self.assertTrue(select.select([p.stdout],[],[],3)[0]);self.assertEqual(set(json.loads(p.stdout.readline())),{'1'})
  finally:p.terminate();p.wait(timeout=2);p.stdout.close();p.stderr.close()
 def test_invalid_configuration_preserves_open_widgets(self):
  self.assertEqual(self.invoke('sync').returncode,0);before=self.state()
  (self.config/'instances.json').write_text('{bad')
  self.assertNotEqual(self.invoke('sync').returncode,0);self.assertEqual(self.state(),before)
if __name__=='__main__':unittest.main()
