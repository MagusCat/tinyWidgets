"""Native controller integration with a test-only IPC transport and an isolated fake Eww."""
import hashlib,json,os,select,socket,struct,subprocess,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ.get('WIDGET_MANAGER_TEST_BIN',str(ROOT/'target/debug/randly-widget-manager')))
FAKE=r'''#!/usr/bin/python3
import json,os,sys
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
  before=len(state['commands']);self.assertEqual(self.invoke('sync').returncode,0)
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
  self.assertEqual(self.invoke('sync').returncode,0);before=self.state();applied=(self.runtime/'eww-widgets-applied.json').read_bytes();source=self.config/'generated/current/style.scss';stamp=source.stat().st_mtime_ns
  result=self.invoke('theme');self.assertEqual(result.returncode,0,result.stderr)
  css=(self.runtime/'theme.css').read_text();self.assertIn('#112233',css)
  (self.config/'_colors.scss').write_text('$primary:#445566;\n');self.assertEqual(self.invoke('theme').returncode,0)
  self.assertIn('#445566',(self.runtime/'theme.css').read_text());self.assertEqual(self.state(),before)
  self.assertEqual((self.runtime/'eww-widgets-applied.json').read_bytes(),applied);self.assertEqual(source.stat().st_mtime_ns,stamp)
 def test_invalid_palette_keeps_last_valid_css(self):
  r=self.invoke('theme');self.assertEqual(r.returncode,0,r.stderr);old=(self.runtime/'theme.css').read_bytes()
  (self.config/'_colors.scss').write_text('$primary: invalidcolor;\n');self.assertNotEqual(self.invoke('theme').returncode,0)
  self.assertEqual((self.runtime/'theme.css').read_bytes(),old);self.assertEqual(self.state()['commands'],[])
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
 def test_invalid_configuration_preserves_open_widgets(self):
  self.assertEqual(self.invoke('sync').returncode,0);before=self.state()
  (self.config/'instances.json').write_text('{bad')
  self.assertNotEqual(self.invoke('sync').returncode,0);self.assertEqual(self.state(),before)
if __name__=='__main__':unittest.main()
