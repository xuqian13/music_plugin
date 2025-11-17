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
from src.common.logger import get_logger

# 导入各个模块的组件
from .modules.image_module import RandomImageAction, RandomImageCommand
from .modules.news_module import (
    News60sTool,
    TodayInHistoryTool,
    NewsCommand,
    HistoryCommand
)
from .modules.music_module import (
    PlayMusicTool,
    MusicCommand,
    ChooseCommand,
    QuickChooseCommand
)

logger = get_logger("entertainment_plugin")


@register_plugin
class EntertainmentPlugin(BasePlugin):
    """娱乐插件 - 整合看看腿、新闻、音乐等功能"""

    plugin_name = "entertainment_plugin"
    plugin_description = "整合了看看腿、新闻、音乐等娱乐功能的统一插件"
    plugin_version = "1.0.0"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp", "Pillow"]

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "modules": "功能模块开关",
        "image": "看看腿功能配置",
        "news": "新闻功能配置",
        "music": "音乐功能配置"
    }

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
            "send_image": ConfigField(
                type=bool,
                default=True,
                description="是否发送新闻图片"
            ),
            "send_text": ConfigField(
                type=bool,
                default=True,
                description="是否发送新闻文本"
            ),
            "max_history_events": ConfigField(
                type=int,
                default=10,
                description="历史事件最大显示数量"
            )
        },
        "music": {
            "api_url": ConfigField(
                type=str,
                default="https://api.vkeys.cn",
                description="音乐API基础URL"
            ),
            "default_source": ConfigField(
                type=str,
                default="netease",
                description="默认音乐源(netease=网易云音乐, qq=QQ音乐)"
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
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        components = []

        # 根据配置启用相应模块
        try:
            image_enabled = self.get_config("modules.image_enabled", True)
            news_enabled = self.get_config("modules.news_enabled", True)
            music_enabled = self.get_config("modules.music_enabled", True)
        except AttributeError:
            # 如果 get_config 方法不存在，默认启用所有模块
            image_enabled = True
            news_enabled = True
            music_enabled = True

        # 看看腿模块
        if image_enabled:
            components.append((RandomImageAction.get_action_info(), RandomImageAction))
            components.append((RandomImageCommand.get_command_info(), RandomImageCommand))
            logger.info("已启用看看腿模块")

        # 新闻模块
        if news_enabled:
            components.append((News60sTool.get_tool_info(), News60sTool))
            components.append((TodayInHistoryTool.get_tool_info(), TodayInHistoryTool))
            components.append((NewsCommand.get_command_info(), NewsCommand))
            components.append((HistoryCommand.get_command_info(), HistoryCommand))
            logger.info("已启用新闻模块")

        # 音乐模块
        if music_enabled:
            components.append((PlayMusicTool.get_tool_info(), PlayMusicTool))
            components.append((MusicCommand.get_command_info(), MusicCommand))
            components.append((ChooseCommand.get_command_info(), ChooseCommand))
            components.append((QuickChooseCommand.get_command_info(), QuickChooseCommand))
            logger.info("已启用音乐模块")

        logger.info(f"娱乐插件加载了 {len(components)} 个组件")
        return components
