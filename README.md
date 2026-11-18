# xlash 安卓开发包

目标：给 Android 17 手机使用、明确执行订阅方规则的 Android 客户端。

本开发包以 Clash Meta for Android v2.11.37 为基础，安装文件名为 `xlash.apk`。目前只完成了本地补丁检查。完整构建和 Android 17 实机验证待执行。

## 已写入补丁的行为

- 强制 `mode: rule`，忽略持久化和会话覆写；UI 的模式切换和覆写入口给出明确说明。
- 保持订阅的 `rules` 顺序、`sub-rules`、策略组和资源集定义，不加入通用分流模板，不转换订阅。
- 拒绝缺少 `rules` 或包含空规则的配置。具体规则语法、节点和规则引用继续由 Mihomo 校验。
- 原配置的 DNS 按上游流程加载；未启用 DNS 时，保留 Android VPN 的默认 DNS 适配并写明原因。因此不宣称配置的每个字节均原样运行。
- 更新时刷新 HTTP 规则集；下载失败或规则集初始化失败返回错误，阻止上游处理目录晋升为已导入配置。校验失败时沿用原配置；断电或磁盘写入中断时的事务恢复尚未实现和验证。
- 关闭外部控制端口及 Unix/Pipe 控制入口，防止外部接口改成全局或直连模式。
- 首页显示当前配置为规则来源。加载后日志记录顶层规则数、规则集数和覆写关闭状态。该日志不等于逐连接规则命中的验证。
- 应用名和桌面名称为 `xlash`，Android 应用 ID 为 `org.subrules.clash.meta`。预览版使用调试签名。

订阅必须返回 Clash/Mihomo 完整 YAML。只有节点列表或 Base64 链接的订阅，没有“订阅方规则”可保留。订阅提供的 MATCH/DIRECT、策略组内的 DIRECT 都属于订阅本身，本补丁不会擅自删除它们。分应用绕过 VPN、Android 系统路由和订阅节点质量不由本补丁保证。

## 文件与使用

- `overlay/`：新增或替换的 Go 和 Android 资源文件，含 Go 回归用例。
- `apply.py`：默认只输出差异；`--write` 才写入。要求干净的 v2.11.37 checkout，所有替换锚点先检查再写文件。
- `build-preview.sh`：在有网络和工具链的机器上下载官方源码、应用补丁、运行 Go 用例并构建调试 APK。尚未实际跑通。
- `tests/upstream-reference.json`：网页读取的上游文件参考，用于验证补丁锚点；不是完整源码。
- `tests/test_patch.py`：补丁应用检查，不验证 Android 应用运行。

在自己的 GitHub 仓库中把本目录的内容放在仓库根目录，然后在 Actions 中运行 **Build xlash**。工作流使用临时构建机和上游指定的工具链。成功后下载名为 `xlash` 的构建产物，解压即可得到 `xlash.apk`。连续两次使用临时构建机可能生成不同调试签名，已有预览版的手机将无法直接覆盖升级。

在联网的 Linux 构建机上，可使用 JDK 21、上游发布流程指定的 MetaCubeX Go 1.26 及 Go 补丁、Android SDK 35、NDK 29.0.14206865、CMake 和 Android Build Tools 35.0.0。运行以下命令会把签名和名称检查通过的通用安装包放在 `artifacts/xlash.apk`。

```bash
export ANDROID_SDK_ROOT=/absolute/path/to/android-sdk
bash build-preview.sh
```

也可在独立的官方 v2.11.37 checkout 先审阅差异：

```bash
python3 apply.py /path/to/ClashMetaForAndroid
python3 apply.py /path/to/ClashMetaForAndroid --write
```

脚本拒绝重复应用；构建失败后在已有 checkout 中排查并重跑具体构建命令，不要删除自己的改动。

## 验证状态与下一步

2026-11-18：只完成补丁参考文件匹配、失败保护和资源 XML 检查。Go 回归用例已编写但未运行，APK 未编译、未安装，Android 17 兼容性未确认。

正式交付前必须完成：

1. 在真实 v2.11.37 checkout 中编译全部改动，检查锁定 Mihomo 子模块的接口和规则集生命周期。
2. 检查 ARM64 APK 的所有原生库 ELF LOAD 对齐及 ZIP 对齐，使用 SDK 的 `zipalign -c -P 16 -v 4 app.apk`；仍需在 16 KB 页面设备/模拟器运行。
3. 在 Android 17 实机验证 VPN 授权、通知被拒绝、前后台切换、熄屏、系统终止、Wi-Fi/蜂窝切换、IPv4/IPv6 和重启。
4. 用受控测试节点验证直连、代理、拒绝、RULE-SET、子规则和 MATCH 的实际流量走向，确认规则顺序与订阅一致。
5. 验证正常更新、超时、HTTP 403/500、空规则、损坏 YAML、缺少策略组、无效规则集内容、磁盘写失败。失败更新后确认旧配置和运行中的 VPN 状态。
6. 检查 Go 规则集初始化是否重复启动定时任务、所有错误分支是否释放资源；连续更新和后台运行做内存检查。
7. 使用自己的长期签名构建发布版，并保存对应完整源码、锁定版本和许可证。

Android 17 的运行兼容和 `targetSdk` 是两件事。此草稿保留上游 target/compile SDK 35，没有通过修改数值宣称已适配 API 37。后续需要结合 Android 17 行为变化测试，再决定目标 SDK 升级。

## 来源与许可证

此为独立修改，非 Clash Verge 或 MetaCubeX 官方版本。保留上游版权与 GPL-3.0 许可证；完整构建时保留上游 LICENSE、NOTICE 和依赖声明。修改日期：2026-11-18。

- 上游：[MetaCubeX/ClashMetaForAndroid v2.11.37](https://github.com/MetaCubeX/ClashMetaForAndroid/tree/v2.11.37)
- 规则语义：[Mihomo 路由规则](https://wiki.metacubex.one/config/rules/)
- 平台：[Android 17 所有应用行为变化](https://developer.android.com/about/versions/17/behavior-changes-all)
- VPN：[Android VPN 开发说明](https://developer.android.com/develop/connectivity/vpn)
