"""
娱乐插件 - Entertainment Plugin

整合了看看腿、新闻、音乐等娱乐功能的统一插件
"""

from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin,
    register_plugin,
    ComponentInfo,
    ConfigField
)
from src.plugin_system.base.config_types import ConfigSection, ConfigLayout, ConfigTab
from src.common.logger import get_logger

# 导入各个模块的组件
from .modules.image_module import RandomImageAction, RandomImageCommand
from .modules.news_module import (
    News60sTool,
    TodayInHistoryTool,
    AINewsTool,
    NewsCommand,
    HistoryCommand,
    AINewsCommand
)
from .modules.music_module import (
    PlayMusicTool,
    MusicCommand,
    ChooseCommand,
    QuickChooseCommand
)
from .modules.ai_draw_module import AIDrawCommand
from .modules.auto_image_tool import AIDrawTool  # 统一的AI绘图工具

logger = get_logger("entertainment_plugin")


@register_plugin
class EntertainmentPlugin(BasePlugin):
    """娱乐插件 - 整合看看腿、新闻、音乐等功能"""

    plugin_name = "entertainment_plugin"
    plugin_description = "整合了看看腿、新闻、音乐等娱乐功能的统一插件"
    plugin_version = "1.0.3"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp", "Pillow"]

    # 配置节描述
    config_section_descriptions = {
        "plugin": ConfigSection(
            title="插件设置",
            description="插件的基础配置",
            icon="🔧",
            collapsed=False,
            order=0
        ),
        "modules": ConfigSection(
            title="功能模块",
            description="选择要启用的娱乐功能模块",
            icon="🎮",
            collapsed=False,
            order=1
        ),
        "image": ConfigSection(
            title="随机图片配置",
            description="配置随机图片API和相关参数",
            icon="🖼️",
            collapsed=True,
            order=2
        ),
        "news": ConfigSection(
            title="新闻资讯配置",
            description="配置60秒新闻和历史上的今天API",
            icon="📰",
            collapsed=True,
            order=3
        ),
        "music": ConfigSection(
            title="音乐点歌配置",
            description="配置音乐点歌相关参数",
            icon="🎵",
            collapsed=True,
            order=4
        ),
        "ai_draw": ConfigSection(
            title="AI绘图配置",
            description="配置AI绘图API和参数",
            icon="🎨",
            collapsed=True,
            order=5
        )
    }

    # 布局配置 - 使用标签页布局
    config_layout = ConfigLayout(
        type="tabs",
        tabs=[
            ConfigTab(id="plugin", title="插件", icon="🔧", sections=["plugin"], order=0),
            ConfigTab(id="modules", title="功能模块", icon="🎮", sections=["modules"], order=1),
            ConfigTab(id="image", title="图片", icon="🖼️", sections=["image"], order=2),
            ConfigTab(id="news", title="新闻", icon="📰", sections=["news"], order=3),
            ConfigTab(id="music", title="音乐", icon="🎵", sections=["music"], order=4),
            ConfigTab(id="ai_draw", title="AI绘图", icon="🎨", sections=["ai_draw"], order=5),
        ]
    )

    # 配置 Schema
    config_schema = {
        "plugin": {
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用插件"
            ),
            "name": ConfigField(
                type=str,
                default="entertainment_plugin",
                description="插件名称"
            ),
            "version": ConfigField(
                type=str,
                default="1.0.0",
                description="插件版本"
            )
        },
        "modules": {
            "image_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用看看腿功能"
            ),
            "news_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用新闻功能"
            ),
            "music_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用音乐功能"
            ),
            "ai_draw_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用AI绘图功能"
            )
        },
        "image": {
            "api_url": ConfigField(
                type=str,
                default="https://www.onexiaolaji.cn/RandomPicture/api/",
                description="图片API地址"
            ),
            "api_key": ConfigField(
                type=str,
                default="qq249663924",
                description="API密钥"
            ),
            "available_classes": ConfigField(
                type=list,
                default=[101, 102, 103, 104],
                description="可用的图片类型列表"
            )
        },
        "news": {
            "api_url": ConfigField(
                type=str,
                default="https://60s.viki.moe/v2/60s",
                description="60秒新闻API地址"
            ),
            "history_api_url": ConfigField(
                type=str,
                default="https://60s.viki.moe/v2/today-in-history",
                description="历史上的今天API地址"
            ),
            "ai_news_api_url": ConfigField(
                type=str,
                default="https://60s.viki.moe/v2/ai-news",
                description="每日AI资讯API地址"
            ),
            "send_image": ConfigField(
                type=bool,
                default=True,
                description="是否发送60秒新闻图片"
            ),
            "send_text": ConfigField(
                type=bool,
                default=True,
                description="是否发送60秒新闻文本"
            ),
            "max_history_events": ConfigField(
                type=int,
                default=10,
                description="历史事件最大显示数量"
            ),
            "max_ai_news": ConfigField(
                type=int,
                default=5,
                description="AI资讯最大显示数量"
            )
        },
        "music": {
            "api_url": ConfigField(
                type=str,
                default="https://api.vkeys.cn",
                description="音乐API基础URL(普通音源)"
            ),
            "vip_api_url": ConfigField(
                type=str,
                default="https://www.littleyouzi.com/api/v2",
                description="VIP音乐API基础URL"
            ),
            "juhe_api_url": ConfigField(
                type=str,
                default="https://api.xcvts.cn/api/music/juhe",
                description="聚合点歌API地址"
            ),
            "default_source": ConfigField(
                type=str,
                default="netease",
                description="默认音乐源(netease=网易云音乐, qq=QQ音乐, netease_vip=网易云VIP, qq_vip=QQ音乐VIP, juhe=聚合点歌)"
            ),
            "timeout": ConfigField(
                type=int,
                default=10,
                description="API请求超时时间(秒)"
            ),
            "max_search_results": ConfigField(
                type=int,
                default=10,
                description="最大搜索结果数"
            ),
            "show_cover": ConfigField(
                type=bool,
                default=True,
                description="是否显示专辑封面"
            ),
            "show_info_text": ConfigField(
                type=bool,
                default=True,
                description="是否显示音乐信息文本"
            ),
            "send_as_voice": ConfigField(
                type=bool,
                default=False,
                description="是否以语音消息发送音乐（true=语音消息，false=音乐卡片）"
            ),
            "enable_quick_choose": ConfigField(
                type=bool,
                default=True,
                description="是否启用数字快捷选择（直接输入1-10选歌）"
            )
        },
        "ai_draw": {
            "api_url": ConfigField(
                type=str,
                default="https://api.xingzhige.com/API/DrawOne/",
                description="AI绘图API地址"
            ),
            "default_prompt": ConfigField(
                type=str,
                default="jk",
                description="默认描述词(当用户未提供时使用)"
            ),
            "timeout": ConfigField(
                type=int,
                default=30,
                description="API请求超时时间(秒)"
            ),
            "selection_mode": ConfigField(
                type=str,
                default="best",
                description="图片选择模式(best=智能最佳匹配, random=随机选择, all=发送全部)"
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        components = []

        # 启动缓存清理任务（防止内存泄漏）
        try:
            from .modules.music_module import start_cache_cleanup
            from .modules.ai_draw_module import start_image_cache_cleanup
            start_cache_cleanup()
            start_image_cache_cleanup()
            logger.info("缓存清理任务已启动")
        except Exception as e:
            logger.warning(f"启动缓存清理任务失败: {e}")

        # 根据配置启用相应模块
        try:
            image_enabled = self.get_config("modules.image_enabled", True)
            news_enabled = self.get_config("modules.news_enabled", True)
            music_enabled = self.get_config("modules.music_enabled", True)
            ai_draw_enabled = self.get_config("modules.ai_draw_enabled", True)
        except AttributeError:
            # 如果 get_config 方法不存在，默认启用所有模块
            image_enabled = True
            news_enabled = True
            music_enabled = True
            ai_draw_enabled = True

        # 看看腿模块
        if image_enabled:
            components.append((RandomImageAction.get_action_info(), RandomImageAction))
            components.append((RandomImageCommand.get_command_info(), RandomImageCommand))
            logger.info("已启用看看腿模块")

        # 新闻模块
        if news_enabled:
            components.append((News60sTool.get_tool_info(), News60sTool))
            components.append((TodayInHistoryTool.get_tool_info(), TodayInHistoryTool))
            components.append((AINewsTool.get_tool_info(), AINewsTool))
            components.append((NewsCommand.get_command_info(), NewsCommand))
            components.append((HistoryCommand.get_command_info(), HistoryCommand))
            components.append((AINewsCommand.get_command_info(), AINewsCommand))
            logger.info("已启用新闻模块")

        # 音乐模块
        if music_enabled:
            components.append((PlayMusicTool.get_tool_info(), PlayMusicTool))
            components.append((MusicCommand.get_command_info(), MusicCommand))
            components.append((ChooseCommand.get_command_info(), ChooseCommand))
            components.append((QuickChooseCommand.get_command_info(), QuickChooseCommand))
            logger.info("已启用音乐模块")

        # AI绘图模块
        if ai_draw_enabled:
            components.append((AIDrawCommand.get_command_info(), AIDrawCommand))
            # 统一的AI绘图工具（支持主动画图、自动配图、换风格）
            components.append((AIDrawTool.get_tool_info(), AIDrawTool))
            logger.info("已启用AI绘图模块（统一Tool + Command架构）")

        logger.info(f"娱乐插件加载了 {len(components)} 个组件")
        return components
