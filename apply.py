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
SERVICE = "service/src/main/java/com/github/kr328/clash/service/"


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
        SERVICE + "StatusProvider.kt": [
            ("""        var serviceRunning: Boolean = false
            set(value) {
                field = value

                shouldStartClashOnBoot = value
            }""", """        @Volatile
        var serviceRunning: Boolean = false
"""),
        ],
        SERVICE + "clash/module/CloseModule.kt": [
            ("import com.github.kr328.clash.common.log.Log\n", "import com.github.kr328.clash.common.log.Log\nimport com.github.kr328.clash.service.StatusProvider\n"),
            ('        Log.d("User request close")', '        StatusProvider.shouldStartClashOnBoot = false\n        Log.d("User request close")'),
        ],
        APP + "remote/StatusClient.kt": [
            ("import android.net.Uri\n", "import android.net.Uri\nimport android.os.Bundle\n"),
            ("""    fun currentProfile(): String? {
        return try {
            val result = context.contentResolver.call(""", """    fun isRunning(): Boolean = queryStatus() != null

    fun queryStatus(): Bundle? {
        return try {
            context.contentResolver.call("""),
            ('\n\n            result?.getString("name")', ''),
            ('Log.w("Query current profile: $e", e)', 'Log.w("Query VPN status: $e", e)'),
        ],
        APP + "remote/Broadcasts.kt": [
            ("    private var registered = false", "    private val status = StatusClient(context)\n    private var registered = false"),
            ("Intents.ACTION_SERVICE_RECREATED -> {\n                    clashRunning = false", "Intents.ACTION_SERVICE_RECREATED -> {\n                    clashRunning = status.isRunning()"),
            ("Intents.ACTION_PROFILE_LOADED -> {\n                    receivers", "Intents.ACTION_PROFILE_LOADED -> {\n                    clashRunning = status.isRunning()\n                    receivers"),
            ("            clashRunning = StatusClient(context).currentProfile() != null", "            registered = true\n            clashRunning = status.isRunning()"),
            ("            context.unregisterReceiver(broadcastReceiver)\n", "            context.unregisterReceiver(broadcastReceiver)\n            registered = false\n"),
        ],
        APP + "TileService.kt": [
            ('        val name = StatusClient(this).currentProfile()\n\n        clashRunning = name != null\n        currentProfile = name ?: ""', '        readVpnStatus()'),
            ("    private fun updateTile() {", """    private fun readVpnStatus() {
        val status = StatusClient(this).queryStatus()
        clashRunning = status != null
        currentProfile = status?.getString("name").orEmpty()
    }

    private fun updateTile() {"""),
            ('                    currentProfile = StatusClient(this@TileService).currentProfile() ?: ""', '                    readVpnStatus()'),
        ],
        APP + "ExternalControlActivity.kt": [
            ("return StatusClient(this).currentProfile() != null", "return StatusClient(this).isRunning()"),
        ],
        DESIGN + "AppSettingsDesign.kt": [
            ("import android.content.Context\n", "import android.content.Context\nimport android.os.Build\n"),
            ("        ReCreateAllActivities\n", "        ReCreateAllActivities,\n        OpenVpnSettings,\n"),
            ("            category(R.string.interface_)\n", """            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                clickable(
                    title = R.string.always_on_vpn_settings,
                    icon = R.drawable.ic_baseline_vpn_lock,
                    summary = R.string.always_on_vpn_summary,
                ) {
                    clicked { requests.trySend(Request.OpenVpnSettings) }
                }
            }

            category(R.string.interface_)
"""),
        ],
        APP + "AppSettingsActivity.kt": [
            ("import android.content.ComponentName\n", "import android.content.ActivityNotFoundException\nimport android.content.ComponentName\nimport android.content.Intent\nimport android.provider.Settings\n"),
            ("import com.github.kr328.clash.design.model.Behavior\n", "import com.github.kr328.clash.design.model.Behavior\nimport com.github.kr328.clash.design.ui.ToastDuration\nimport com.github.kr328.clash.design.R as DesignR\n"),
            ("""                    ApplicationObserver.createdActivities.forEach {
                        it.recreate()
                    }""", """                    when (it) {
                        AppSettingsDesign.Request.ReCreateAllActivities ->
                            ApplicationObserver.createdActivities.forEach { activity -> activity.recreate() }
                        AppSettingsDesign.Request.OpenVpnSettings -> {
                            try {
                                startActivity(Intent(Settings.ACTION_VPN_SETTINGS))
                            } catch (_: ActivityNotFoundException) {
                                design.showToast(DesignR.string.always_on_vpn_unavailable, ToastDuration.Long)
                            }
                        }
                    }"""),
        ],
        "app/src/main/AndroidManifest.xml": [
            ('android:icon="@mipmap/ic_launcher"', 'android:icon="@mipmap/xlash_launcher"'),
            ('android:roundIcon="@mipmap/ic_launcher_round"', 'android:roundIcon="@mipmap/xlash_launcher"'),
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
    # The proxy and VPN services share a single runtime in the background process.
    for name in ("ClashService", "TunService"):
        edits[SERVICE + name + ".kt"] = [
            ("    private var reason: String? = null\n", "    private var reason: String? = null\n    private var ownsRuntime = false\n"),
            ("                    config.onEvent {\n", "                    config.onEvent {\n                        StatusProvider.shouldStartClashOnBoot = false\n"),
            ('        } catch (e: Exception) {\n            Log.e("Create clash runtime:', '        } catch (e: Exception) {\n            if (e is kotlinx.coroutines.CancellationException) throw e\n            StatusProvider.shouldStartClashOnBoot = false\n            Log.e("Create clash runtime:'),
            ("        StatusProvider.serviceRunning = true\n\n", ""),
            ("        runtime.launch()\n", """        ownsRuntime = true
        StatusProvider.serviceRunning = true
        StatusProvider.shouldStartClashOnBoot = true
        runtime.launch()
"""),
            ("    override fun onDestroy() {\n", """    override fun onDestroy() {
        if (!ownsRuntime) {
            super.onDestroy()
            return
        }

"""),
            ("    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {\n        sendClashStarted()", "    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {\n        if (!ownsRuntime) return START_NOT_STICKY\n\n        sendClashStarted()"),
            ("        cancelAndJoinBlocking()\n", "        cancelAndJoinBlocking()\n        StatusProvider.currentProfile = null\n"),
        ]
    edits[SERVICE + "TunService.kt"] += [
        ("        return super.onStartCommand(intent, flags, startId)\n", "        return START_STICKY\n"),
        ("    override fun onDestroy() {\n", """    override fun onRevoke() {
        StatusProvider.shouldStartClashOnBoot = false
        super.onRevoke()
    }

    override fun onDestroy() {
"""),
    ]
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
