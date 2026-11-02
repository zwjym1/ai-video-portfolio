#!/bin/bash
# 用法：bash templates/psych_series/init_ep.sh projects/EP-YYYYMMDD-NN
# 把模板的 remotion/ 和 audio/ 拷进期目录（已存在的文件不覆盖），node_modules 复用 EP01 那份（同版本 remotion 4.0.539）。
set -e
EP=${1:?期目录}; TPL=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$TPL/../.." && pwd)
mkdir -p "$EP"/{script,vo,subs,sfx/bgm,final/beatcheck,review/qc_final,deliver}
cp -rn "$TPL/remotion" "$EP/"; mkdir -p "$EP/audio"; cp -n "$TPL/audio/"* "$EP/audio/"
[ -e "$EP/remotion/node_modules" ] || ln -s "$(readlink -f "$ROOT/projects/EP-20261031-01/remotion/node_modules")" "$EP/remotion/node_modules"
echo "ok：$EP（改 remotion/src/episode.json、Film.tsx、Cover.tsx 的 Visual、audio/mix_config.json）"
