# FeedMerge

FeedMerge 订阅公开信息源，用 DeepSeek Flash 为当天有更新的各来源各写一句中文摘要，在同一行附原文链接，并用 VitePress 发布。

## 运行

在项目目录使用 Python 3.13 和 Node.js 24。

~~~powershell
python -m pip install -r requirements.txt
npm ci
python -m feedmerge --check-sources
# 在当前环境注入 DEEPSEEK_API_KEY 后再生成简报。
python -m feedmerge
npm run build
npm run preview
~~~

默认汇总北京时间昨天发布的内容。使用 `--date YYYY-MM-DD` 指定日期，`--refresh` 更新已有日期，`--render-only` 单独重建站点。日报 Markdown 在 `site/daily/`，VitePress 产物在 `site/.vitepress/dist/`。测试命令为 `python -m unittest discover -s tests`。

## 订阅

[sources.json](sources.json) 保存原始清单。站点的订阅页显示自动采集、参考资料和待接入状态。已核验的 RSS/Atom、公开播客节目页和即刻话题使用轻量适配器。暂无可靠地址或权限的条目保留在清单。播客摘要基于节目简介。

同一作者在其他平台的公开入口会标明平台。X 时间线仅保留所订阅账号的原帖。Tibo 的时间线在 FxEmbed 暂时不可用时会尝试备用 RSS。腾讯云公开专栏使用页面里的文章摘要和北京时间发布日期。

新增可信 RSS 时，为对应条目填写 `url`，把 `adapter` 设为 `rss`、`mode` 设为 `active`，再运行 `--check-sources`。私有订阅地址和访问凭证应留在本机。

## GitHub Pages

将仓库 Pages 的构建来源设为 GitHub Actions，在仓库 Actions Secrets 配置 `DEEPSEEK_API_KEY`。工作流每天北京时间 08:13 尝试汇总昨天，也支持手动触发。首次部署由主分支推送触发。

每次部署从已发布站点读取 `archive-data.json`，合并历史摘要后构建整站。当天已存在的日报默认复用，指定 `--refresh` 才重新采集。摘要生成失败时工作流在部署前停止，上一版站点仍可访问。公开站点仅发布简短摘要、原文链接和来源状态。
