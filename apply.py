#!/usr/bin/env python3
"""Apply a reviewable, version-locked patch to a fresh official CMFA checkout.

No network access, command execution, subscription URLs, or signing credentials.
All anchors and overlay collisions are checked before any source file is changed.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
TAG = "v2.11.37"
GO = "core/src/main/golang/native/config/"
DESIGN = "design/src/main/java/com/github/kr328/clash/design/"
APP = "app/src/main/java/com/github/kr328/clash/"


def replace_once(source: str, before: str, after: str, path: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"{path}: upstream anchor changed or patch already applied; no files written")
    return source.replace(before, after, 1)


def planned_changes(checkout: Path) -> dict[str, str]:
    edits: dict[str, list[tuple[str, str]]] = {
        "core/src/main/golang/native/app/dns.go": [
            ("package app\n", "//go:build android\n\npackage app\n"),
        ],
        GO + "process.go": [
            ("\tpatchOverride,\n", "\tpatchOverride,\n\tpatchSubscriptionRules,\n"),
            ("\tif !cfg.DNS.Enable {\n", '\tif !cfg.DNS.Enable {\n\t\tlog.Infoln("订阅未启用 DNS：使用 Android VPN 默认 DNS 适配；分流规则仍来自配置")\n'),
        ],
        GO + "load.go": [
            ("\tlogDns(rawCfg)\n", '\t// Do not log DNS URLs: they may contain credentials.\n'),
            ("\thub.ApplyConfig(cfg)\n\n\tapp.ApplySubtitlePattern", '\thub.ApplyConfig(cfg)\n\tlog.Infoln("规则来源：当前配置；mode=rule；顶层规则=%d；规则集=%d；本地覆写=关闭", len(rawCfg.Rule), len(rawCfg.RuleProvider))\n\n\tapp.ApplySubtitlePattern'),
        ],
        GO + "fetch.go": [
            ("\treturn response.Body, fetchHeader{", '\tif response.StatusCode < 200 || response.StatusCode >= 300 {\n\t\tresponse.Body.Close()\n\t\treturn nil, fetchHeader{}, fmt.Errorf("订阅或规则集服务器返回 HTTP %d", response.StatusCode)\n\t}\n\treturn response.Body, fetchHeader{'),
            ("\tforEachProviders(rawCfg, func(index int, total int, name string, provider map[string]any, prefix string) {", "\tvar providerErr error\n\tforEachProviders(rawCfg, func(index int, total int, name string, provider map[string]any, prefix string) {\n\t\tif providerErr != nil { return }"),
            ("\t\tif _, err := os.Stat(ps); err == nil {", "\t\t// Refresh HTTP rule sets on subscription update, even if an old cache exists.\n\t\tif _, err := os.Stat(ps); err == nil && !(force && prefix == RULES) {"),
            ("\t\turl, err := U.Parse(us)\n\t\tif err != nil {\n\t\t\treturn\n\t\t}", '\t\turl, err := U.Parse(us)\n\t\tif err != nil {\n\t\t\tproviderErr = fmt.Errorf("资源集 %q 的地址无效，配置未应用", name)\n\t\t\treturn\n\t\t}'),
            ("\t\t_, _ = fetch(url, ps)\n\t})", '\t\tif _, err := fetch(url, ps); err != nil {\n\t\t\tproviderErr = fmt.Errorf("资源集 %q 下载失败；请检查网络或订阅，配置未应用", name)\n\t\t}\n\t})\n\tif providerErr != nil { return providerErr }'),
            ("\tdestroyProviders(cfg)\n\n\treturn nil", "\tdefer destroyProviders(cfg)\n\treturn validateSubscriptionProviders(cfg)"),
        ],
        DESIGN + "MainDesign.kt": [
            ("binding.profileName = name", "binding.profileName = name?.let { context.getString(R.string.subscription_rule_source, it) }"),
            ("TunnelState.Mode.Rule -> context.getString(R.string.rule_mode)", "TunnelState.Mode.Rule -> context.getString(R.string.subscription_rule_mode)"),
        ],
        DESIGN + "component/ProxyMenu.kt": [
            ("""            when (mode) {
                null -> findItem(R.id.dont_modify).isChecked = true
                TunnelState.Mode.Direct -> findItem(R.id.direct_mode).isChecked = true
                TunnelState.Mode.Global -> findItem(R.id.global_mode).isChecked = true
                TunnelState.Mode.Rule -> findItem(R.id.rule_mode).isChecked = true
                else -> {}
            }""", """            listOf(R.id.dont_modify, R.id.direct_mode, R.id.global_mode).forEach {
                findItem(it).isVisible = false
            }
            findItem(R.id.rule_mode).apply {
                isChecked = true
                isEnabled = false
                title = context.getString(R.string.subscription_rule_mode)
            }"""),
        ],
        APP + "ProxyActivity.kt": [
            ("""                            design.showModeSwitchTips()

                            withClash {
                                val o = queryOverride(Clash.OverrideSlot.Session)

                                o.mode = it.mode

                                patchOverride(Clash.OverrideSlot.Session, o)
                            }""", """                            design.showToast(
                                com.github.kr328.clash.design.R.string.subscription_rule_locked,
                                com.github.kr328.clash.design.ui.ToastDuration.Long
                            )"""),
        ],
        APP + "SettingsActivity.kt": [
            ("startActivity(OverrideSettingsActivity::class.intent)", "design.showToast(\n                                com.github.kr328.clash.design.R.string.subscription_rule_locked,\n                                com.github.kr328.clash.design.ui.ToastDuration.Long\n                            )"),
        ],
        "app/src/main/AndroidManifest.xml": [
            ('android:name=".MainActivityAlias"\n            android:exported="true"', 'android:name=".MainActivityAlias"\n            android:exported="true"\n            android:label="@string/application_name"'),
        ],
        "build.gradle.kts": [
            ('?: "com.github.metacubex.clash"', '?: "org.subrules.clash"'),
            ('versionName = "2.11.36"', 'versionName = "0.1.0-subscription-preview"'),
            ('versionCode = 211036', 'versionCode = 1'),
            ('setProperty("archivesBaseName", "cmfa-$versionName")', 'setProperty("archivesBaseName", "xlash-$versionName")'),
            ('resValue("string", "launch_name", "@string/launch_name_meta")', 'resValue("string", "launch_name", "xlash")'),
            ('resValue("string", "launch_name", "@string/launch_name_alpha")', 'resValue("string", "launch_name", "xlash")'),
            ('resValue("string", "application_name", "@string/application_name_meta")', 'resValue("string", "application_name", "xlash")'),
            ('resValue("string", "application_name", "@string/application_name_alpha")', 'resValue("string", "application_name", "xlash")'),
        ],
    }
    result = {}
    for path, changes in edits.items():
        target = checkout / path
        if target.is_symlink() or not target.resolve().is_relative_to(checkout.resolve()):
            raise ValueError(f"Unsafe source path: {path}")
        source = target.read_text(encoding="utf-8")
        for before, after in changes:
            source = replace_once(source, before, after, path)
        result[path] = source
    # The only intentional replacement is the upstream override implementation.
    for source in sorted((ROOT / "overlay").rglob("*")):
        if not source.is_file():
            continue
        path = source.relative_to(ROOT / "overlay").as_posix()
        target = checkout / path
        if target.is_symlink() or not target.resolve().is_relative_to(checkout.resolve()):
            raise ValueError(f"Unsafe overlay path: {path}")
        if target.exists() and path != GO + "override.go":
            raise ValueError(f"Overlay collision: {path}; no files written")
        result[path] = source.read_text(encoding="utf-8")
    return result


def verify_checkout(checkout: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()
    if git("rev-parse", "HEAD") != git("rev-parse", f"{TAG}^{{commit}}"):
        raise ValueError(f"Use a fresh checkout of official CMFA {TAG}")
    if git("status", "--porcelain"):
        raise ValueError("Checkout must be clean; keep local work separate")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--write", action="store_true", help="apply; default prints a reviewable diff")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    verify_checkout(checkout)
    changes = planned_changes(checkout)
    for path, after in changes.items():
        target = checkout / path
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        old_name = "a/" + path if target.exists() else "/dev/null"
        print("".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=old_name, tofile="b/" + path)), end="")
    if args.write:
        for path, after in changes.items():
            target = checkout / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(after, encoding="utf-8")


if __name__ == "__main__":
    main()
