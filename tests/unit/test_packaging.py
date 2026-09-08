from __future__ import annotations

import configparser
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from alchemy import __version__

ROOT = Path(__file__).parents[2]


class PackagingTests(unittest.TestCase):
    def test_python_metadata_uses_pep639_and_installs_desktop_assets(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["license"], "GPL-3.0-or-later")
        self.assertEqual(metadata["project"]["license-files"], ["LICENSE"])
        data_files = metadata["tool"]["setuptools"]["data-files"]
        self.assertIn("share/applications", data_files)
        self.assertIn("share/metainfo", data_files)
        self.assertIn("share/icons/hicolor/scalable/apps", data_files)

    def test_desktop_appstream_and_icon_assets_are_well_formed(self) -> None:
        desktop = configparser.ConfigParser(interpolation=None)
        desktop.read(ROOT / "packaging" / "io.github.youssof20.Alchemy.desktop")
        self.assertEqual(desktop["Desktop Entry"]["Exec"], "alchemy gui")
        self.assertEqual(desktop["Desktop Entry"]["Terminal"], "false")

        metainfo = ET.parse(
            ROOT / "packaging" / "io.github.youssof20.Alchemy.metainfo.xml"
        ).getroot()
        self.assertEqual(metainfo.findtext("id"), "io.github.youssof20.Alchemy")
        self.assertEqual(metainfo.findtext("project_license"), "GPL-3.0-or-later")
        release = metainfo.find("releases/release")
        self.assertIsNotNone(release)
        assert release is not None
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(release.attrib["version"], metadata["project"]["version"])
        self.assertEqual(__version__, metadata["project"]["version"])
        ET.parse(ROOT / "packaging" / "io.github.youssof20.Alchemy.svg")

    def test_native_package_paths_are_explicit_and_do_not_fetch_installers(self) -> None:
        pkgbuild = (ROOT / "packaging" / "arch" / "PKGBUILD").read_text(encoding="utf-8")
        control = (ROOT / "debian" / "control").read_text(encoding="utf-8")
        rules = (ROOT / "debian" / "rules").read_text(encoding="utf-8")

        self.assertIn("python -m build --wheel --no-isolation", pkgbuild)
        self.assertIn('python -m installer --destdir="$pkgdir"', pkgbuild)
        self.assertNotIn("curl", pkgbuild)
        self.assertIn("python3-pyside6.qtwidgets", control)
        self.assertIn("export PYBUILD_NAME=alchemy", rules)
        self.assertIn("--buildsystem=pybuild", rules)

    def test_sdist_manifest_explicitly_excludes_internal_planning_material(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertNotIn("include *.md", manifest.splitlines())
        self.assertNotIn("CONTEXT", manifest)
        self.assertNotIn("PROMPT", manifest)


if __name__ == "__main__":
    unittest.main()
