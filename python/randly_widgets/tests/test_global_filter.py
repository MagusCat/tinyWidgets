import ast,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from randly_widgets import runtime
from randly_widgets.adapters.wayfire import is_global_widget,widget_matches_workspace
from test_widgets import widget

class GlobalFilterTests(unittest.TestCase):
    def test_global_aliases_and_workspace_assignments_remain_compatible(self):
        for value in ('Global','Todos','all','*','','global, Workspace 2'):
            self.assertTrue(is_global_widget(widget(workspace=value)))
        for value in ('Workspace 1','Workspace 2, Workspace 3','1,2'):
            self.assertFalse(is_global_widget(widget(workspace=value)))
        self.assertTrue(widget_matches_workspace(widget(workspace='Global'),5,(1,1)))

    def test_editor_global_mode_never_matches_workspace_only_widgets(self):
        path=Path(__file__).parents[1]/'editor/interaction.py';tree=ast.parse(path.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='is_widget_visible')
        namespace={'W':SimpleNamespace(is_global_widget=is_global_widget,widget_matches_workspace=widget_matches_workspace)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(path),'exec'),namespace)
        editor=SimpleNamespace(filter_ws=None,current_ws_coords=(0,0))
        self.assertTrue(namespace['is_widget_visible'](editor,widget(workspace='Global')))
        self.assertFalse(namespace['is_widget_visible'](editor,widget(workspace='Workspace 1')))
        editor.filter_ws=1
        self.assertTrue(namespace['is_widget_visible'](editor,widget(workspace='Workspace 1')))

    def test_background_watcher_and_editor_global_request_select_same_instances(self):
        from test_motion_regressions import ReconcileTests
        for mode in (None,'global',True):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td,ExitStack() as stack:
                root=Path(td);widgets=[widget('g',workspace='Global'),widget('local',workspace='Workspace 1'),widget('other',workspace='Workspace 2')]
                state=ReconcileTests.harness(self,stack,root,widgets,{w['id']:runtime.spec(w) for w in widgets})
                (root/'eww-widgets-editing').write_text('global')
                self.assertTrue(runtime.sync(mode));self.assertEqual(state['active'],{'g'})

    def test_cli_transports_global_filter_instead_of_all(self):
        from randly_widgets import cli
        with patch('randly_widgets.paths.ensure_runtime'),patch.object(runtime,'sync',return_value=True) as sync:
            self.assertEqual(cli.main(['sync','global']),0)
            self.assertEqual(sync.call_args.args[0],'global')
