#!/usr/bin/env bash
# 对 corpus 全部片子跑 qoder-flash 盲审（盒上跑；3 路并行）。用法: run_subjective_corpus.sh r1 [id ...]
cd "$(dirname "$0")"; R=${1:-r1}; shift
IDS=${@:-$(/workspace/.venv-review/bin/python -c "import json;print(' '.join(v['id'] for v in json.load(open('corpus/corpus.json'))['videos']))")}
for id in $IDS; do
  [ -s out/$id/subjective_$R.json ] && grep -q '"ok": true' out/$id/subjective_$R.json && continue
  echo "$id"
done | xargs -P 3 -I{} /workspace/.venv-review/bin/python lib/subjective.py --sheets out/{}/sheets --asr corpus/asr/{}.json --out out/{}/subjective_$R.json
