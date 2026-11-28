// 使用 GitHub Pages 仓库路径部署，也支持根路径本地预览。
import { defineConfig } from 'vitepress'

const base = process.env.BASE_PATH || '/'

export default defineConfig({
  lang: 'zh-CN',
  title: 'FeedMerge',
  description: '订阅来源的每日信息摘要',
  base,
  head: [['link', { rel: 'icon', type: 'image/png', href: `${base}icon.png` }]],
  cleanUrls: false,
  themeConfig: {
    logo: '/icon.png',
    nav: [
      { text: '每日简报', link: '/' },
      { text: '订阅来源', link: '/sources' }
    ],
    search: { provider: 'local' }
  }
})
