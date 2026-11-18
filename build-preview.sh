#!/usr/bin/env bash
# Build a local debug preview only. No upload, publication, or release signing.
set -euo pipefail
bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${1:-$bundle_dir/source}"
sdk_dir="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"

for tool in git python3 java javac go; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "缺少构建工具：$tool。请先准备 JDK 21、Go 和 Android SDK。" >&2
        exit 2
    fi
done
if [[ -z "$sdk_dir" || ! -d "$sdk_dir/platforms/android-35" || ! -d "$sdk_dir/ndk/29.0.14206865" ]]; then
    echo '请设置 ANDROID_SDK_ROOT，安装 platforms;android-35 和 ndk;29.0.14206865，以及 CMake、Build Tools。' >&2
    exit 2
fi
build_tools="$sdk_dir/build-tools/35.0.0"
for tool in aapt apksigner zipalign; do
    if [[ ! -x "$build_tools/$tool" ]]; then
        echo "缺少 Android Build Tools 35.0.0 中的 $tool" >&2
        exit 2
    fi
done
if [[ ! -d "$source_dir" ]]; then
    git clone --branch v2.11.37 --single-branch https://github.com/MetaCubeX/ClashMetaForAndroid.git "$source_dir"
fi
# A failed dependency download can be retried without reapplying the patch.
applied_patch="$bundle_dir/applied.diff"
if [[ ! -s "$applied_patch" ]] || ! git -C "$source_dir" apply --reverse --check "$applied_patch" 2>/dev/null; then
    python3 "$bundle_dir/apply.py" "$source_dir" --write > "$applied_patch.tmp"
    mv "$applied_patch.tmp" "$applied_patch"
fi
git -C "$source_dir" submodule update --init --recursive
if [[ ! -e "$source_dir/local.properties" ]]; then
    printf 'sdk.dir=%s\n' "$sdk_dir" > "$source_dir/local.properties"
fi
install -m 644 /etc/ssl/certs/ca-certificates.crt "$source_dir/core/src/foss/golang/clash/component/ca/ca-certificates.crt"

(
    cd "$source_dir/core/src/main/golang"
    go test -tags 'foss with_gvisor cmfa' ./native/config
)
(
    cd "$source_dir"
    # Gradle can otherwise merge the assets before the download task completes.
    bash ./gradlew --no-daemon app:downloadGeoFiles
    bash ./gradlew --no-daemon app:assembleMetaDebug -x app:downloadGeoFiles
)
apk_dir="$source_dir/app/build/outputs/apk/meta/debug"
apk_name=$(python3 - "$apk_dir/output-metadata.json" <<'PY'
import json
from pathlib import Path
import sys

metadata = json.loads(Path(sys.argv[1]).read_text())
names = [e['outputFile'] for e in metadata['elements'] if not e['filters']]
if len(names) != 1 or Path(names[0]).name != names[0]:
    sys.exit('找不到唯一的通用 APK')
print(names[0])
PY
)
apk="$apk_dir/$apk_name"
"$build_tools/apksigner" verify "$apk"
"$build_tools/zipalign" -c -P 16 4 "$apk"
badging=$("$build_tools/aapt" dump badging "$apk")
python3 - "$badging" <<'PY'
import re
import sys

labels = re.findall(r"^application-label(?:-[^:]+)?:'([^']*)'$", sys.argv[1], re.M)
launcher = re.search(r"^launchable-activity:.*?label='([^']*)'", sys.argv[1], re.M)
if not labels or set(labels) != {'xlash'} or not launcher or launcher[1] not in ('', 'xlash'):
    sys.exit('APK 应用或桌面名称校验失败')
PY
mkdir -p "$bundle_dir/artifacts"
install -m 644 "$apk" "$bundle_dir/artifacts/xlash.apk.tmp"
mv "$bundle_dir/artifacts/xlash.apk.tmp" "$bundle_dir/artifacts/xlash.apk"
echo "$bundle_dir/artifacts/xlash.apk"
