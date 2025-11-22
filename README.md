# 娱乐插件 (Entertainment Plugin)

整合了看看腿、新闻、音乐、AI绘图等娱乐功能的统一插件。

## 📋 功能模块

### 🖼️ 看看腿功能
调用随机图片API获取腿部图片

**触发方式：**
- 关键词：看看腿、腿、看腿、康康腿、看看大长腿、大长腿
- 命令：`/kankan` 或 `/看腿 [类型]`

**示例：**
```
/kankan          # 随机获取图片
/kankan 101      # 获取指定类型图片
/看腿 102
```

### 📰 新闻功能
提供每天60秒读懂世界的新闻摘要和历史上的今天

**触发方式：**
- 命令：`/news` 或 `/新闻` - 查看每天60秒新闻
- 命令：`/history` 或 `/历史` - 查看历史上的今天
- Tool：可供LLM调用

**示例：**
```
/news           # 查看今日新闻
/新闻
/history        # 查看历史上的今天
/历史
```

### 🎵 音乐功能
支持多个音乐平台点歌，包括网易云、QQ音乐、VIP音质和聚合点歌

**触发方式：**
- 搜索：`/music [音源] 歌曲名`
- 选择：`/choose 序号`
- 快捷：直接输入数字 1-10（搜索后60秒内有效）
- Tool：可供LLM调用

**支持的音乐源：**
- `netease` - 网易云音乐（普通音质）
- `qq` - QQ音乐（普通音质）
- `netease_vip` - 网易云音乐VIP（高品质）
- `qq_vip` - QQ音乐VIP（高品质）
- `juhe` - 聚合点歌（整合多平台）

**示例：**
```
/music 晴天                    # 使用默认音源搜索
/music netease 勾指起誓        # 网易云音乐搜索
/music qq 青花瓷               # QQ音乐搜索
/music netease_vip 稻香        # 网易云VIP音质
/music qq_vip 七里香           # QQ音乐VIP音质
/music juhe 起风了             # 聚合点歌（多平台）
/choose 1                      # 选择第1首歌
1                              # 快捷选择第1首歌
```

### 🎨 AI绘图功能
基于AI的智能图片生成，支持多种描述词

**触发方式：**
- 关键词：AI绘图、画图、绘图、生成图片、画一张
- 命令：`/draw` 或 `/绘图` 或 `/画图 [描述词]`

**选择模式：**
- `best` - 智能分析匹配度，选择最相关的一张（推荐）
- `random` - 随机选择一张
- `all` - 发送全部图片（最多4张）

**示例：**
```
AI绘图 可爱的猫咪              # 关键词触发
画一张 美丽的风景
/draw jk                      # 命令触发
/绘图 动漫少女
/画图 赛博朋克风格城市
```

## 📁 目录结构

```
entertainment_plugin/
├── __init__.py              # 包初始化
├── plugin.py                # 主插件文件
├── config.toml              # 配置文件
├── _manifest.json           # 组件清单
├── README.md                # 说明文档
├── modules/                 # 功能模块
│   ├── __init__.py
│   ├── image_module.py      # 看看腿功能
│   ├── news_module.py       # 新闻功能
│   ├── music_module.py      # 音乐功能（支持5种音源）
│   └── ai_draw_module.py    # AI绘图功能
└── utils/                   # 共用工具
    ├── __init__.py
    ├── api_client.py        # API请求封装
    └── image_generator.py   # 图片生成工具
```

## ⚙️ 配置说明

在 `config.toml` 中可以配置：

### 功能模块开关
```toml
[modules]
image_enabled = true        # 看看腿功能
news_enabled = true         # 新闻功能
music_enabled = true        # 音乐功能
ai_draw_enabled = true      # AI绘图功能
```

### 看看腿配置
```toml
[image]
api_url = "https://www.onexiaolaji.cn/RandomPicture/api/"
api_key = "qq249663924"
available_classes = [101, 102, 103, 104]
```

### 新闻配置
```toml
[news]
api_url = "https://60api.09cdn.xyz/v2/60s"
history_api_url = "https://60api.09cdn.xyz/v2/today-in-history"
send_image = true
send_text = false
max_history_events = 10
```

### 音乐配置
```toml
[music]
api_url = "https://api.vkeys.cn"                           # 普通音源API
vip_api_url = "https://www.littleyouzi.com/api/v2"         # VIP音源API
juhe_api_url = "https://api.xcvts.cn/api/music/juhe"       # 聚合点歌API
default_source = "netease"                                 # 默认音源
timeout = 30
max_search_results = 10
show_cover = false
show_info_text = false
send_as_voice = true                                       # true=语音, false=卡片
enable_quick_choose = true                                 # 数字快捷选择
quick_choose_timeout = 60                                  # 快捷选择有效期（秒）
```

### AI绘图配置
```toml
[ai_draw]
api_url = "https://api.xingzhige.com/API/DrawOne/"
default_prompt = "jk"                                      # 默认描述词
timeout = 30
selection_mode = "best"                                    # best/random/all
```

## 🎯 组件列表

| 组件类型 | 组件名称 | 功能描述 |
|---------|---------|---------|
| Action | RandomImageAction | 关键词触发看看腿 |
| Command | RandomImageCommand | 命令触发看看腿 |
| Tool | News60sTool | 获取60秒新闻（可供LLM调用） |
| Tool | TodayInHistoryTool | 获取历史上的今天（可供LLM调用） |
| Command | NewsCommand | 查询新闻命令 |
| Command | HistoryCommand | 查询历史命令 |
| Tool | PlayMusicTool | 播放音乐（可供LLM调用） |
| Command | MusicCommand | 音乐搜索命令 |
| Command | ChooseCommand | 选择歌曲命令 |
| Command | QuickChooseCommand | 快捷选择命令（数字1-10） |
| Action | AIDrawAction | 关键词触发AI绘图 |
| Command | AIDrawCommand | 命令触发AI绘图 |

## 📦 依赖项

Python包依赖：
- `aiohttp` - 异步HTTP请求
- `Pillow` - 图片生成（可选，用于生成歌曲列表图片）

## 🔧 安装

1. 确保依赖包已安装：
```bash
pip install aiohttp Pillow
```

2. 将插件放入 MaiBot 的 plugins 目录

3. 重启 MaiBot

## ✨ 特性

- ✅ 模块化设计，易于维护
- ✅ 统一的API客户端，代码复用
- ✅ 灵活的配置，可单独开关功能
- ✅ 保留所有原有命令和关键词
- ✅ 完善的错误处理和日志记录
- ✅ 支持5种音乐源（网易云、QQ音乐、VIP音质、聚合点歌）
- ✅ 智能缓存，快捷选择提升用户体验
- ✅ AI绘图智能匹配算法，选择最相关图片
- ✅ 多平台音乐聚合，自动重试机制

## 🎵 音乐源说明

### 普通音源
- **网易云音乐 (netease)**: 免费音质，稳定可靠
- **QQ音乐 (qq)**: 免费音质，曲库丰富

### VIP音源
- **网易云VIP (netease_vip)**: 高品质音频，需要VIP API
- **QQ音乐VIP (qq_vip)**: 高品质音频，需要VIP API

### 聚合点歌
- **聚合点歌 (juhe)**: 整合多个音乐平台（酷我、网易等），智能选择最佳源

## 📝 版本历史

### v1.2.0 (2025-11-23)
- 新增聚合点歌功能，支持多平台音乐源
- 优化VIP音乐源URL提取逻辑
- 修复VIP音乐播放链接获取问题

### v1.1.0 (2024)
- 新增AI绘图功能
- 新增VIP音乐源支持（网易云VIP、QQ音乐VIP）
- 添加智能图片选择算法
- 优化音乐搜索缓存机制

### v1.0.0 (2024)
- 初始版本
- 整合看看腿、新闻、音乐三大功能
- 实现模块化架构
- 统一配置管理

## 👨‍💻 作者

Augment Agent

## 📄 许可证

与 MaiBot 项目保持一致
