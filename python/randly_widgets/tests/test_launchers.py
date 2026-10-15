import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from randly_widgets import chest,launchers
from randly_widgets.providers import Context,load_provider
from randly_widgets.registry import SCHEMA


def widget(wid='one',kind='apps',**opts):
    return {'id':wid,'window':kind,'opts':opts}


class LauncherTests(unittest.TestCase):
    def test_launching_widgets_have_no_preselected_applications(self):
        for kind in ('apps','chest','button'):
            defaults={key:default for key,_,_,default,*_ in SCHEMA[kind]['options']}
            self.assertEqual(launchers.entries(widget(kind=kind,**defaults)),[])
        self.assertEqual(next(o[3] for o in SCHEMA['button']['options'] if o[0]=='command'),'')
        self.assertEqual(launchers.app_data(widget()),{'apps':[],'empty':True})

    def test_chest_provider_returns_data_and_isolates_instance_slots(self):
        provider=load_provider('chest','fixture')
        first=widget(kind='chest',launchers=json.dumps([{'name':'One','cmd':'first'}]))
        second=widget('two','chest',launchers=json.dumps([None,{'name':'Two','cmd':'second'}]))
        with patch.object(provider,'read_event',return_value={}):
            a=provider.collect(Context(first,{}));b=provider.collect(Context(second,{}))
        self.assertIsInstance(a,dict);self.assertEqual(a['rows'][0][0]['label'],'One')
        self.assertEqual(b['rows'][0][1]['label'],'Two');self.assertFalse(b['rows'][0][0]['used'])
        self.assertEqual(len(a['rows']),3);self.assertEqual(len(a['rows'][0]),9)
        json.dumps(a)

    def test_legacy_chest_migration_preserves_empty_slots_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'chest.conf';source.write_text('X | Original | printf original\n-\nY | Next | printf next\n')
            widgets=[widget(kind='chest'),widget('configured','chest',launchers='[]'),widget('new','apps')]
            self.assertTrue(launchers.migrate_chest(widgets,source))
            targets=launchers.entries(widgets[0]);self.assertIsNone(targets[1]);self.assertEqual(targets[2]['cmd'],'printf next')
            self.assertEqual(launchers.entries(widgets[1]),[]);self.assertNotIn('launchers',widgets[2]['opts'])
            self.assertFalse(launchers.migrate_chest(widgets,source))

    def test_custom_command_launches_only_selected_instance(self):
        first=widget(launchers='[{"name":"First","cmd":"printf first"}]')
        second=widget('two',launchers='[{"name":"Second","cmd":"printf second"}]')
        before=copy.deepcopy(first)
        with patch('randly_widgets.launchers.subprocess.Popen') as launch:
            launchers.launch(second,0)
            self.assertEqual(launch.call_args.args[0],['sh','-c','printf second'])
        self.assertEqual(first,before)
        with self.assertRaises(ValueError):launchers.launch(second,4)

    def test_desktop_entries_use_gio_without_interpreting_exec(self):
        DesktopAppInfo=launchers.desktop_class()
        app=Mock()
        with patch.object(DesktopAppInfo,'new',return_value=app),patch('subprocess.Popen',side_effect=AssertionError('No shell for desktop entries')):
            launchers.launch(widget(launchers='[{"desktop_id":"org.example.App.desktop"}]'),0)
            app.launch.assert_called_once_with([],None)
        with patch.object(DesktopAppInfo,'new',return_value=None):
            with self.assertRaises(ValueError):launchers.launch(widget(launchers='[{"desktop_id":"gone.desktop"}]'),0)

    def test_invalid_targets_do_not_invent_commands(self):
        for value in ('not json','{}','["kitty"]','[{"desktop_id":"/tmp/app.desktop"}]','[{"desktop_id":"app.desktop","cmd":"whoami"}]','[{}]'):
            with self.subTest(value=value),self.assertRaises(ValueError):launchers.parse(value)
        self.assertEqual(launchers.entries(widget(apps='firefox,thunar'))[0]['cmd'],'firefox')

    def test_legacy_render_stays_json_but_provider_contract_is_mapping(self):
        with patch.object(chest,'parse',return_value=[]):
            self.assertEqual(json.loads(chest.render())['count'],0)
            self.assertIsInstance(chest.data(),dict)
