import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", ROOT / "apply.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class PatchTests(unittest.TestCase):
    """These test patch application, not Android or the Go runtime."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkout = Path(self.temp.name)
        self.files = json.loads((ROOT / "tests/upstream-reference.json").read_text())["files"]
        for name, text in self.files.items():
            path = self.checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def test_reference_version_can_be_patched_without_mutating_dry_run(self):
        changes = patcher.planned_changes(self.checkout)
        self.assertEqual(len(changes), 13)
        for name, text in self.files.items():
            self.assertEqual((self.checkout / name).read_text(), text)

    def test_source_drift_fails_before_any_write(self):
        name = "build.gradle.kts"
        p = self.checkout / name
        p.write_text(p.read_text().replace("versionCode = 211036", "versionCode = 999999"))
        with self.assertRaises(ValueError):
            patcher.planned_changes(self.checkout)
        for name in self.files:
            if name != "build.gradle.kts":
                self.assertEqual((self.checkout / name).read_text(), self.files[name])

    def test_all_flavors_label_launcher_and_application_xlash(self):
        build = patcher.planned_changes(self.checkout)["build.gradle.kts"]
        for label in ("launch_name", "application_name"):
            lines = [s.strip() for s in build.splitlines() if f'resValue("string", "{label}",' in s]
            self.assertEqual(lines, [f'resValue("string", "{label}", "xlash")'] * 2)

    def test_existing_overlay_file_is_not_overwritten(self):
        p = self.checkout / patcher.GO / "subscription_rules.go"
        p.write_text("user work")
        with self.assertRaises(ValueError):
            patcher.planned_changes(self.checkout)
        self.assertEqual(p.read_text(), "user work")

    def test_symlink_outside_checkout_is_rejected(self):
        p = self.checkout / "build.gradle.kts"
        p.unlink()
        p.symlink_to(ROOT / "apply.py")
        with self.assertRaises(ValueError):
            patcher.planned_changes(self.checkout)

    def test_patching_twice_is_rejected(self):
        for name, text in patcher.planned_changes(self.checkout).items():
            p = self.checkout / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        with self.assertRaises(ValueError):
            patcher.planned_changes(self.checkout)

    def test_rule_guard_is_reachable_and_mode_writes_are_removed(self):
        changes = patcher.planned_changes(self.checkout)
        source = changes[patcher.GO + "process.go"]
        self.assertLess(source.index("\tpatchSubscriptionRules,"), source.index("\tpatchProviders,"))
        self.assertNotIn("o.mode = it.mode", changes[patcher.APP + "ProxyActivity.kt"])
        self.assertNotIn("OverrideSettingsActivity::class.intent", changes[patcher.APP + "SettingsActivity.kt"])
        self.assertIn("isEnabled = false", changes[patcher.DESIGN + "component/ProxyMenu.kt"])

    def test_provider_errors_gate_success(self):
        source = patcher.planned_changes(self.checkout)[patcher.GO + "fetch.go"]
        self.assertNotIn("_, _ = fetch(url, ps)", source)
        self.assertIn("if providerErr != nil { return providerErr }", source)
        self.assertIn("defer destroyProviders(cfg)", source)
        self.assertIn("return validateSubscriptionProviders(cfg)", source)

    def test_resource_files_parse_and_keys_match(self):
        resources = [ET.parse(p).getroot() for p in (ROOT / "overlay").rglob("*.xml")]
        self.assertEqual(len(resources), 2)
        self.assertEqual({s.attrib["name"] for s in resources[0]}, {s.attrib["name"] for s in resources[1]})


if __name__ == "__main__":
    unittest.main()
