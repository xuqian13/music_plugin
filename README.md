# 🎵 网易云音乐点歌插件

基于网易云音乐API的智能点歌插件，支持音乐搜索和点歌功能，为 MaiCore 提供丰富的音乐体验。

## 功能特性

- 🎵 **智能音乐搜索**：基于关键词自动识别用户点歌意图
- 🎤 **多种触发方式**：支持Action自动触发和Command手动触发两种模式
- 🎧 **丰富音乐信息**：显示歌曲、歌手、专辑、时长、音质等详细信息
- 🖼️ **专辑封面展示**：自动获取并显示专辑封面图片
- 🎶 **多种发送模式**：支持音乐卡片和语音消息两种发送方式
- ⚙️ **灵活配置选项**：支持音质选择、显示选项等多种配置
- 🔧 **组件控制**：支持独立启用/禁用Action和Command组件
- 📝 **完善日志记录**：详细的操作日志和错误处理
- ⚡ **异步处理**：高性能异步API调用，响应迅速

## 安装配置

### 1. 依赖安装

插件需要以下Python依赖：
```bash
pip install aiohttp requests
```

### 2. 配置说明

插件会自动生成 `config.toml` 配置文件，主要配置项：

```toml
[plugin]
enabled = true

[components]
action_enabled = true    # 是否启用Action组件
command_enabled = true   # 是否启用Command组件

[api]
base_url = "https://api.vkeys.cn"
timeout = 10

[music]
default_quality = "9"    # 默认音质等级(1-9)
max_search_results = 10

[features]
show_cover = true        # 是否显示专辑封面
show_download_link = false
show_info_text = true    # 是否显示音乐信息文本
send_as_voice = false    # 是否以语音消息发送音乐（true=语音消息，false=音乐卡片）
```

## 使用方法

### Action触发（自动模式）

当消息中包含以下关键词时，插件会自动触发音乐搜索：
- "音乐"、"歌曲"、"点歌"、"听歌"
- "music"、"song"、"播放"、"来首"

**示例：**
- "我想听音乐"
- "点首歌"
- "来首music"
- "播放歌曲"

### Command触发（手动模式）

使用命令格式直接点歌：

```
/music 勾指起誓
/music 晴天
/music Jay Chou 青花瓷
```

## 发送模式

插件支持两种音乐发送模式：

### 音乐卡片模式（默认）
- 发送音乐卡片，支持播放控制
- 配置：`send_as_voice = false`

### 语音消息模式
- 发送语音消息，直接播放音乐
- 配置：`send_as_voice = true`
- 需要API返回有效的音乐播放链接

## API支持

使用 vkeys.cn 提供的网易云音乐API服务：
- **API地址**: https://api.vkeys.cn/v2/music/netease
- **认证方式**: 无需认证
- **支持平台**: 网易云音乐
- **音质选项**: 1-9级（1为标准音质，9为超高音质）

## 版本信息

- **版本**: 1.0.0
- **作者**: 靓仔
- **许可证**: AGPL-v3.0
- **依赖**: aiohttp, requests
- **兼容性**: MaiCore 0.9.0
