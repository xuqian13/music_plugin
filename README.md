# Music Plugin - 网易云音乐点歌插件

基于网易云音乐 API 的智能点歌插件，支持多音乐源、智能搜索和音乐推荐。

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/xuqian13/music_plugin)
[![License](https://img.shields.io/badge/license-AGPL--v3.0-green.svg)](LICENSE)

---

## 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [安装部署](#安装部署)
- [使用指南](#使用指南)
- [配置说明](#配置说明)
- [高级功能](#高级功能)
- [故障排除](#故障排除)
- [开发文档](#开发文档)

---

## 功能特性

### 核心功能

- **多音乐源支持**：支持网易云音乐和 QQ 音乐双平台
- **智能搜索**：快速搜索音乐，返回精确的搜索列表
- **列表选择**：支持图片或文本形式展示搜索结果
- **快捷选择**：直接输入数字 1-10 快速选歌
- **智能推荐**：根据当前播放歌曲推荐相似音乐
- **会话隔离**：群聊和私聊的搜索结果互不干扰

### 技术特性

- 全异步 API 调用（基于 aiohttp）
- 指数退避重试机制，确保稳定性
- 30 分钟搜索结果缓存
- 音乐源适配器架构，易于扩展
- 中文字体自动检测与回退
- 完善的日志记录和错误处理

---

## 快速开始

### 基本使用

```bash
# 1. 搜索音乐（返回列表）
/music 晴天

# 2. 选择歌曲播放
/choose 1

# 或者直接输入数字快捷选择
1
```

### 使用示例

```
用户: /music 勾指起誓
Bot:  [显示10首歌曲列表]
      #1 勾指起誓 - 洛天依,乐正绫
      #2 勾指起誓（女生版） - 泥鳅Niko
      ...

用户: /choose 1
Bot:  🎵 【正在播放】
      🎤 歌曲：勾指起誓
      🎙️ 歌手：洛天依,乐正绫
      💿 专辑：勾指起誓
      ⏱️ 时长：03:45
      📊 音质：Hi-Res
```

---

## 安装部署

### 1. 系统要求

- Python 3.8+
- MaiBot 框架 0.9.0+

### 2. 安装依赖

#### 必需依赖

```bash
pip3 install aiohttp
```

#### 可选依赖（用于生成图片列表）

```bash
# Python 库
pip3 install Pillow

# 中文字体（Ubuntu/Debian）
sudo apt-get install fonts-noto-cjk

# 中文字体（CentOS/RHEL）
sudo yum install google-noto-cjk-fonts

# macOS（通常已自带中文字体）
# 无需额外安装
```

### 3. 插件配置

将插件放置到 MaiBot 的 `plugins/` 目录下，编辑 `config.toml` 文件进行配置（参见[配置说明](#配置说明)）。

---

## 使用指南

### 命令列表

| 命令 | 描述 | 示例 |
|------|------|------|
| `/music <歌名>` | 搜索音乐并返回列表 | `/music 晴天` |
| `/choose <序号>` | 从列表中选择歌曲 | `/choose 1` |
| `<数字>` | 快捷选择（1-10） | `1` |

### 使用场景

#### 场景 1：搜索 + 列表选择

适合不确定具体歌曲时使用。

```
用户: /music 南山南
Bot:  [显示搜索列表]
      #1 南山南 - 马頔
      #2 南山南 - 王晰
      #3 南山南 - 张磊
      ...

用户: /choose 2
Bot:  [播放王晰版本的南山南]
```

#### 场景 2：快捷数字选择

在搜索后可直接输入数字快速选歌。

```
用户: /music 青花瓷
Bot:  [显示搜索列表]

用户: 1
Bot:  [直接播放第1首]
```

#### 场景 3：群聊多人使用

每个用户的搜索结果独立存储，互不干扰。

```
用户A: /music 南山南
用户B: /music 成都

用户A: /choose 1    # 播放南山南
用户B: /choose 2    # 播放成都的第2个搜索结果
```

### 搜索列表展示

#### 图片列表（推荐）

当系统安装了中文字体时，将自动生成美观的图片列表。

特点：
- 清晰的视觉展示
- 交替背景色，便于阅读
- 包含歌曲、歌手、专辑信息

#### 文本列表（回退方案）

当无中文字体或 PIL 库未安装时，自动使用文本列表。

```
🎵 搜索结果：南山南 [网易云音乐]
找到 10 首歌曲
========================================

#1  南山南
     歌手: 马頔
     专辑: 孤鸟的歌

#2  南山南
     歌手: 王晰
     专辑: 王晰

========================================
💡 输入 /choose <序号> 来选择歌曲
```

---

## 配置说明

配置文件位于 `config.toml`。

### 音乐源配置

```toml
[music]
# 默认音乐源 (netease=网易云音乐, qq=QQ音乐)
default_source = "netease"

# 网易云音乐音质等级 (1-9)
netease_quality = "7"

# QQ音乐音质等级 (0-16)
qq_quality = "14"

# 搜索结果数量
max_search_results = 10
```

#### 音质等级说明

**网易云音乐 (netease_quality)**

| 等级 | 音质 | 码率 |
|------|------|------|
| 1 | 标准音质 | 64kbps |
| 5 | SQ 无损 | 320kbps |
| 7 | Hi-Res 高解析 | - |
| 9 | 母带音质 | - |

**QQ音乐 (qq_quality)**

| 等级 | 音质 | 说明 |
|------|------|------|
| 0 | 标准 | 128kbps |
| 8 | 高品质 | 320kbps |
| 14 | 无损 | FLAC |
| 16 | Hi-Res | 高解析无损 |

推荐设置：网易云 `7` 或 `9`，QQ音乐 `14`

### API 配置

```toml
[api]
# API 基础 URL
base_url = "https://api.vkeys.cn"

# 请求超时时间（秒）
timeout = 10

# 重试次数
retries = 3

# 重试延迟（秒，指数退避）
base_delay = 1.0
```

### 功能开关配置

```toml
[features]
# 是否显示专辑封面
show_cover = true

# 是否显示下载链接
show_download_link = false

# 是否显示音乐信息文本
show_info_text = true

# 发送方式（true=语音消息, false=音乐卡片）
send_as_voice = false

# 最大封面图片大小（字节）
max_image_size = 5242880

# 是否启用数字快捷选择
enable_quick_choose = true

# 是否启用相似推荐
enable_recommendation = true

# 推荐歌曲数量
max_recommendations = 5
```

---

## 高级功能

### 1. 多音乐源切换

插件支持网易云音乐和 QQ 音乐两个音乐源。通过修改配置文件切换：

```toml
[music]
default_source = "qq"  # 切换到QQ音乐
```

切换后，所有搜索和播放都将使用新的音乐源。

### 2. 相似推荐

播放歌曲后，插件会自动推荐该歌手的其他歌曲：

```
🎵 【正在播放】
🎤 歌曲：晴天
🎙️ 歌手：周杰伦
...

💡 相似推荐（周杰伦的其他歌曲）：
1. 七里香 - 七里香
2. 稻香 - 魔杰座
3. 彩虹 - 我很忙
4. 简单爱 - 范特西
5. 夜曲 - 十一月的萧邦

输入 /music 周杰伦 查看更多
```

### 3. 搜索结果缓存

搜索结果会缓存 30 分钟，在此期间可以随时选择，无需重新搜索。

缓存机制：
- 缓存时长：30 分钟
- 存储位置：内存
- 隔离级别：按用户+会话隔离

### 4. 会话隔离

群聊和私聊的搜索结果完全隔离：

- 私聊缓存 key：`music_search_{user_id}`
- 群聊缓存 key：`music_search_{group_id}_{user_id}`

这确保了在群聊中多人同时使用时不会互相干扰。

---

## 故障排除

### Q: 搜索列表显示为方框？

**A**: 系统缺少中文字体，插件会自动回退到文本列表。

**解决方案**：
```bash
# Ubuntu/Debian
sudo apt-get install fonts-noto-cjk

# CentOS/RHEL
sudo yum install google-noto-cjk-fonts
```

### Q: 提示"没有找到搜索记录"？

**A**: 搜索缓存已过期（30分钟）或未搜索过。

**解决方案**：重新使用 `/music 歌名` 搜索。

### Q: 群里多人使用会冲突吗？

**A**: 不会。每个用户的搜索结果独立存储在不同的缓存 key 中。

### Q: 无法播放音乐？

**A**: 可能的原因：

1. **API 限流**：稍后重试
2. **网络问题**：检查网络连接
3. **音质不可用**：降低音质等级
4. **歌曲版权**：尝试其他歌曲或切换音乐源

**解决方案**：
```toml
# 降低音质
[music]
netease_quality = "5"  # 从7降到5

# 或切换音乐源
default_source = "qq"
```

### Q: 如何关闭封面图片？

**A**: 修改配置文件：
```toml
[features]
show_cover = false
```

### Q: 图片列表加载失败？

**A**: 检查以下几点：

1. PIL 库是否安装：`pip3 install Pillow`
2. 中文字体是否存在：`ls /usr/share/fonts/`
3. 检查日志中的 `[ImageGen]` 相关错误

如果无法解决，插件会自动使用文本列表。

### Q: API 请求频繁超时？

**A**: 增加超时时间和重试次数：
```toml
[api]
timeout = 20
retries = 5
```

---

## 开发文档

### 项目结构

```
plugins/music_plugin/
├── plugin.py                           # 主插件文件
├── config.toml                         # 配置文件
├── _manifest.json                      # 插件清单
├── README.md                           # 本文档
├── UPDATE.md                           # 更新日志
├── MULTI_SOURCE_GUIDE.md              # 多音乐源指南
└── LICENSE                            # 许可证
```

### 核心组件

#### 1. 音乐源适配器

插件使用适配器模式支持多个音乐源：

- `MusicSourceAdapter`：适配器基类
- `NeteaseAdapter`：网易云音乐适配器
- `QQMusicAdapter`：QQ 音乐适配器

**扩展新的音乐源**：

```python
class CustomAdapter(MusicSourceAdapter):
    def __init__(self, api_url: str, timeout: int):
        super().__init__(api_url, timeout)
        self.source_name = "custom"
        self.source_display_name = "自定义音乐源"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10):
        # 实现搜索逻辑
        pass

    async def get_music_detail(self, keyword: str, choose: int, quality: str):
        # 实现获取详情逻辑
        pass

    def normalize_music_info(self, data: dict):
        # 实现数据标准化
        pass
```

#### 2. 命令组件

- `MusicCommand`：音乐搜索命令 (`/music`)
- `ChooseCommand`：选择歌曲命令 (`/choose`)
- `QuickChooseCommand`：快捷选择命令 (数字 `1-10`)

#### 3. 工具方法

- `call_music_api()`：调用音乐 API（带重试）
- `search_music_list()`：搜索音乐列表
- `download_image_base64()`：下载图片并转 base64
- `generate_music_list_image()`：生成列表图片
- `generate_music_list_text()`：生成列表文本

### API 接口

本插件使用 [vkeys.cn](https://api.vkeys.cn) 提供的音乐 API。

#### 网易云音乐

**搜索列表**
```
GET https://api.vkeys.cn/v2/music/netease?word=歌名&page=1&num=10
```

**获取详情**
```
GET https://api.vkeys.cn/v2/music/netease?word=歌名&choose=1&quality=7
```

#### QQ 音乐

**搜索列表**
```
GET https://api.vkeys.cn/v2/music/tencent?word=歌名&page=1&num=10
```

**获取详情**
```
GET https://api.vkeys.cn/v2/music/tencent?word=歌名&choose=1&quality=14
```

### 缓存机制

```python
# 缓存结构
{
    "search_key": {
        "keyword": "晴天",
        "results": [...],  # 搜索结果列表
        "source": "netease",  # 音乐源
        "timestamp": 1234567890  # 时间戳
    }
}

# 缓存 TTL：30 分钟
_CACHE_TTL = 1800
```

### 日志级别

- `DEBUG`：详细的调试信息（API 参数、返回数据等）
- `INFO`：一般信息（搜索、播放成功等）
- `WARNING`：警告信息（API 失败、图片下载失败等）
- `ERROR`：错误信息（异常、重试失败等）

---

## 许可证

本项目采用 AGPL-v3.0 许可证。详见 [LICENSE](./LICENSE) 文件。

---

## 贡献者

- **作者**：[靓仔](https://github.com/xuqian13)
- **贡献者**：欢迎提交 PR 和 Issue

---

## 相关链接

- [MaiBot 框架](https://github.com/yourusername/MaiBot)
- [插件开发文档](https://docs.maibot.com)
- [API 文档](https://api.vkeys.cn)
- [问题反馈](https://github.com/xuqian13/music_plugin/issues)

---

**享受音乐！**
