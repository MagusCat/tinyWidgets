"""Installation regressions: personal data survives upgrades; no GUI is started."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tinywidgets_install', ROOT/'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallTests(unittest.TestCase):
    def test_existing_instances_profiles_and_custom_modules_survive_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home/'.config/eww'
            config.mkdir(parents=True)
            (config/'.modular-active').write_text('1')
            (config/'eww.yuck').write_text('existing entrypoint')
            (config/'instances.json').write_text('{"personal":true}')
            (config/'profiles').mkdir()
            (config/'profiles/my.json').write_text('keep')
            (config/'widgets/custom').mkdir(parents=True)
            (config/'widgets/custom/provider.py').write_text('keep')
            binary = home/'.local/bin/widgetctl'
            binary.parent.mkdir(parents=True)
            binary.write_text('old launcher')
            backup = installer.install(home)
            self.assertEqual((config/'instances.json').read_text(), '{"personal":true}')
            self.assertEqual((config/'profiles/my.json').read_text(), 'keep')
            self.assertEqual((config/'widgets/custom/provider.py').read_text(), 'keep')
            self.assertEqual((backup/'.local/bin/widgetctl').read_text(), 'old launcher')
            self.assertIn('randly-widget-manager', binary.read_text())
            self.assertTrue(json.loads((backup/'manifest.json').read_text())['installed'])
    def test_foreign_eww_configuration_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home/'.config/eww'
            config.mkdir(parents=True)
            (config/'eww.yuck').write_text('another project')
            with self.assertRaises(RuntimeError):
                installer.install(home)
            self.assertFalse((home/'.local').exists())
            self.assertEqual((config/'eww.yuck').read_text(), 'another project')
    def test_fresh_install_builds_a_generation_without_starting_a_daemon(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            installer.install(home)
            config = home/'.config/eww'
            self.assertTrue((config/'generated/current/view.yuck').exists())
            self.assertTrue((config/'widgets/chest/assets/chest-open.png').exists())
            self.assertTrue((config/'widgets/github/assets/avatar-fallback.png').exists())
            self.assertFalse((config/'assets').exists())
            self.assertEqual(json.loads((config/'instances.json').read_text())['widgets'], [])
            self.assertEqual(list(home.rglob("editor-sync-service.json")), [])

if __name__ == '__main__':
    unittest.main()
