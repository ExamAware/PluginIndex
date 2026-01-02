插件源

## 生成聚合清单（Python）

```sh
python3 -m pip install -r tools/requirements.txt
python3 tools/fetch_npm.py   # 从 npm 刷新版本/完整性信息
python3 tools/generate_index.py
```

- 分散清单位于 `index/plugins/`，支持 `.yml/.yaml/.json`。
- `base.json` 中的 `DownloadMirrors` 会写入聚合结果的 `mirrors` 字段。