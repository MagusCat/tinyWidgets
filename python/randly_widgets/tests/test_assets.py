import json
import shutil
import tempfile
import unittest
from pathlib import Path
from randly_widgets.assets import asset_path, validate_assets
from randly_widgets.composer import render, BuildError
from randly_widgets.paths import EWW_DIR
from randly_widgets.registry import Registry


class AssetTests(unittest.TestCase):
    def test_component_paths_cannot_escape_or_follow_external_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);component=root/'widget';(component/'assets').mkdir(parents=True)
            (component/'assets/image.png').write_bytes(b'fixture')
            (root/'outside.png').write_bytes(b'external')
            (component/'assets/link.png').symlink_to(root/'outside.png')
            self.assertEqual(asset_path(component,'image.png'),component/'assets/image.png')
            for name in ('../outside.png',str(root/'outside.png'),'link.png','missing.png'):
                with self.subTest(name=name),self.assertRaises(ValueError):asset_path(component,name)
            with self.assertRaises(ValueError):validate_assets(component,['image.png','image.png'])
            with self.assertRaises(ValueError):validate_assets(component,'image.png')

    def test_components_install_without_a_shared_assets_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(Path(EWW_DIR)/'shared',root/'shared')
            shutil.copy2(Path(EWW_DIR)/'_colors.scss',root/'_colors.scss')
            for kind in ('chest','github'):
                shutil.copytree(Path(EWW_DIR)/'widgets'/kind,root/'widgets'/kind)
            self.assertEqual(Registry(root).errors,{})
            yuck,_=render(root,widgets=[])
            self.assertIn(str(root/'widgets/chest/assets/chest-open.png'),yuck)
            self.assertIn(str(root/'widgets/github/assets/avatar-fallback.png'),yuck)
            self.assertNotIn(str(root/'assets'),yuck)
            (root/'widgets/chest/assets/chest-open.png').unlink()
            self.assertIn('chest',Registry(root).errors)
            with self.assertRaises(BuildError):render(root,widgets=[])

    def test_provider_asset_uses_its_own_component_and_declared_inventory(self):
        from randly_widgets.providers import Context
        context=Context({'window':'github'}, {})
        self.assertTrue(context.asset('avatar-fallback.png').endswith('/github/assets/avatar-fallback.png'))
        with self.assertRaises(ValueError):context.asset('chest-open.png')

    def test_github_manages_cache_and_preserves_existing_data(self):
        from unittest.mock import patch
        from randly_widgets import github
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);legacy=home/'.cache';legacy.mkdir()
            (legacy/'eww-github-avatar.png').write_bytes(b'old avatar')
            folder=home/'owned/profile/github'
            with patch.object(Path,'home',return_value=home),patch.multiple(github,CACHE_DIR=folder,CACHE=str(folder/'status.json'),AVATAR=str(folder/'avatar.png'),AVATAR_RAW=str(folder/'raw.png')):
                github.prepare_cache()
                self.assertEqual((folder/'avatar.png').read_bytes(),b'old avatar')
                (folder/'avatar.png').write_bytes(b'new avatar')
                github.prepare_cache()
                self.assertEqual((folder/'avatar.png').read_bytes(),b'new avatar')

    def test_animation_budget_settings_round_trip_and_clamp(self):
        from unittest.mock import patch
        from randly_widgets import appearance
        with tempfile.TemporaryDirectory() as tmp,patch.object(appearance,'ANIM_FILE',str(Path(tmp)/'animation.json')):
            appearance.save_animation(anim_in='vortex',when='workspace',delay_in=240,workspace_delay=700,max_parallel=3,fps=20,palette_animation=True)
            settings=appearance.load_animation()
            self.assertEqual((settings['anim_in'],settings['delay_in'],settings['workspace_delay'],settings['max_parallel'],settings['fps']),('vortex',240,700,3,20))
            appearance.save_animation(max_parallel=999,fps=1,delay_in=-50)
            settings=appearance.load_animation();self.assertEqual((settings['max_parallel'],settings['fps'],settings['delay_in']),(16,12,0))
