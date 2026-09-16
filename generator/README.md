# 生成器

静态站生成器：读 `../data/精选库.json`（相对本目录），渲染整个站点到发布仓根。纯 Python 标准库，零依赖。

## 用法

```bash
# 正式构建（默认读 <发布仓>/data/精选库.json，输出到 <发布仓>/）
/opt/homebrew/bin/python3 generator/build.py

# 试跑（自定义数据源 + 输出目录，不碰发布仓）
/opt/homebrew/bin/python3 generator/build.py /tmp/seed.json /tmp/testsite
```

## 产物

| 文件 | 说明 |
|---|---|
| `index.html` | 首页：数据内嵌为 `<script id="seed-data" type="application/json">`，由 `assets/app.js` 客户端渲染 |
| `about.html` | 关于 / 免责 / 纠错 / AI 辅助标注 |
| `404.html` | 回首页 |
| `assets/style.css` | 移动端优先样式（375px 起步，桌面为加宽版） |
| `assets/app.js` | 双视图 / 分类筛选 / 按天分组（UTC→UTC+8）/ 卡片展开 / 页脚新鲜度 |

## 改名 / 改品牌

站名、标语、域名、纠错链接等全部集中在 `build.py` 顶部 `CONFIG` 字典，改一处后重新构建即可。

## 数据契约

见项目根《建站规格书》。要点：`items[]` 每条须有 `title_zh` 与 `url`，缺者构建时丢弃并告警；时间字段一律 UTC，页面统一按北京时间（UTC+8）显示。

数据文件不存在或不可解析时构建直接失败（exit 2）；空态发布可先写入 `{"generated_at_utc":"<当前UTC>","items":[]}`。
