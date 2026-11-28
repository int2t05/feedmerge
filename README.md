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

同一作者在其他平台有公开入口时，订阅清单会标明采集平台。

| 平台 | 采集方式 | 部署与权限 |
| --- | --- | --- |
| X | 读取 FxEmbed RSS，只保留所订阅账号的原帖。FxEmbed 不可用时尝试备用 RSS。 | 当前公开入口免密钥，第三方可用性会影响采集。 |
| 微信公众号 | 使用经实测的公开 RSS，保留公众号文章链接。 | 已收录的账号可直接读取。其余账号需要可用的订阅地址。 |
| 即刻、小宇宙 | 读取公开分享页随页面返回的原帖或免费节目简介。 | 无需另建服务，播客基于简介生成摘要。 |
| 独立站、公开专栏 | 优先使用 RSS 或 Atom，也可读取公开栏目。产品沉思录和陀螺科技取近期文章正文，腾讯云取专栏列表里的摘要。 | 无需另建服务，公开页面变化时需更新对应解析。 |
| 知乎 | 待确认作者主页或专栏链接，再验证能返回正文、日期和原文链接的订阅入口。 | 当前清单的两个条目尚未接入。 |
| 飞书 Wiki、文档和多维表格 | 可通过开放平台查询 Wiki 节点、读取文档或查询表格记录。 | 需要应用或用户的资源读取权限。当前清单中的飞书条目作为参考入口。见[飞书 Wiki API](https://open.feishu.cn/document/server-docs/docs/wiki-v2/wiki-overview)和[多维表格权限说明](https://open.feishu.cn/document/docs/bitable-v1/faq)。 |

采集和 VitePress 构建均可直接在 GitHub Actions 运行，也可在云主机上用定时任务运行同一套命令。当前采集入口无需购买 API 密钥，DeepSeek 摘要按 API 用量计费。

新增可信 RSS 时，为对应条目填写 `url`，把 `adapter` 设为 `rss`、`mode` 设为 `active`，再运行 `--check-sources`。私有订阅地址和访问凭证应留在本机。

### 未收录的公众号

已验证的公开 RSS 可直接用于日报。若账号未收录，可用 [WeRSS 自托管](https://github.com/rachelos/we-mp-rss/blob/main/README.zh-CN.md) 生成 RSS，服务需要微信扫码授权。若已有[今天看啥](https://www.jintiankansha.me/help/start)订阅，可用其 RSS 或 [MCP](https://mcp.jintiankansha.me/main/limits) 读取已订阅内容。平台对内容更新和使用额度设有限制。

已在今天看啥确认「孔某人的低维认知」有专栏。MCP 的 HTTPS 入口在无凭证时返回 401。WeRSS 和今天看啥暂未接入 FeedMerge，仍需用获准访问的账号验证最近文章的正文、发布日期和微信原文链接。

## GitHub Pages

将仓库 Pages 的构建来源设为 GitHub Actions，在仓库 Actions Secrets 配置 `DEEPSEEK_API_KEY`。工作流每天北京时间 08:13 尝试汇总昨天，12:37 再尝试一次。当天已有日报时复用存档，支持手动触发。首次部署由主分支推送触发。

每次部署从已发布站点读取 `archive-data.json`，合并历史摘要后构建整站。当天已存在的日报默认复用，指定 `--refresh` 才重新采集。摘要生成失败时工作流在部署前停止，上一版站点仍可访问。公开站点仅发布简短摘要、原文链接和来源状态。
