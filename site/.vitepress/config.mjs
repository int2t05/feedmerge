// 使用 GitHub Pages 仓库路径部署，也支持根路径本地预览。
import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'zh-CN',
  title: 'FeedMerge',
  description: '订阅来源的每日信息摘要',
  base: process.env.BASE_PATH || '/',
  cleanUrls: false,
  themeConfig: {
    nav: [
      { text: '每日简报', link: '/' },
      { text: '订阅来源', link: '/sources' }
    ],
    search: { provider: 'local' }
  }
})
