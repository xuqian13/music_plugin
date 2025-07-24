"""
Music Plugin - 网易云音乐点歌插件

基于网易云音乐API的智能点歌插件，支持音乐搜索和点歌功能。

功能特性：
- 智能音乐搜索和推荐
- 支持关键词自动触发和命令手动触发
- 丰富的音乐信息展示
- 专辑封面显示
- 灵活的配置选项

使用方法：
- Action触发：发送包含"音乐"、"歌曲"等关键词的消息
- Command触发：/music 歌曲名

API接口：https://api.vkeys.cn/v2/music/netease
"""

from typing import List, Tuple, Type, Optional
import aiohttp
import json
import requests
import base64
from src.plugin_system.apis import send_api, chat_api
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ChatMode
)
from src.plugin_system.base.config_types import ConfigField
from src.common.logger import get_logger

logger = get_logger("music_plugin")

# ===== 智能消息发送工具 =====
async def smart_send(chat_stream, message_data):
    """智能发送不同类型的消息，并返回实际发包内容"""
    message_type = message_data.get("type", "text")
    content = message_data.get("content", "")
    options = message_data.get("options", {})
    target_id = (chat_stream.group_info.group_id if getattr(chat_stream, 'group_info', None)
                else chat_stream.user_info.user_id)
    is_group = getattr(chat_stream, 'group_info', None) is not None
    # 调试用，记录实际发包内容
    packet = {
        "message_type": message_type,
        "content": content,
        "target_id": target_id,
        "is_group": is_group,
        "typing": options.get("typing", False),
        "reply_to": options.get("reply_to", ""),
        "display_message": options.get("display_message", "")
    }
    print(f"[调试] smart_send 发包内容: {json.dumps(packet, ensure_ascii=False)}")
    # 实际发送
    success = await send_api.custom_message(
        message_type=message_type,
        content=content,
        target_id=target_id,
        is_group=is_group,
        typing=options.get("typing", False),
        reply_to=options.get("reply_to", ""),
        display_message=options.get("display_message", "")
    )
    return success, packet

# ===== Action组件 =====

class MusicSearchAction(BaseAction):
    """音乐搜索Action - 智能音乐推荐"""

    action_name = "music_search"
    action_description = "搜索并推荐音乐"

    # 关键词激活
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD

    activation_keywords = ["音乐", "歌曲", "点歌", "听歌", "music", "song", "播放", "来首"]
    keyword_case_sensitive = False

    action_parameters = {
        "song_name": "要搜索的歌曲名称",
        "quality": "音质要求(1-9，可选)"
    }
    action_require = [
        "用户想要听音乐时使用",
        "用户询问音乐相关信息时使用",
        "用户想要点歌时使用"
    ]
    associated_types = ["text"]

    def get_log_prefix(self) -> str:
        """获取日志前缀"""
        return f"[MusicSearchAction]"

    async def execute(self) -> Tuple[bool, str]:
        """执行音乐搜索"""
        try:
            # 获取参数
            song_name = self.action_data.get("song_name", "").strip()
            quality = self.action_data.get("quality", "")

            if not song_name:
                await self.send_text("❌ 请告诉我你想听什么歌曲~")
                return False, "缺少歌曲名称"

            # 从配置获取设置
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            default_quality = self.get_config("music.default_quality", "9")

            # 使用默认音质如果未指定
            if not quality:
                quality = default_quality

            logger.info(f"{self.get_log_prefix()} 开始搜索音乐，歌曲：{song_name[:50]}..., 音质：{quality}")

            # 调用音乐API
            music_info = await self._call_music_api(api_url, song_name, quality, timeout)

            if music_info:
                # 发送音乐信息
                await self._send_music_info(music_info)
                logger.info(f"{self.get_log_prefix()} 音乐搜索成功")
                return True, f"成功找到音乐：{music_info.get('song', '未知')[:30]}..."
            else:
                await self.send_text("❌ 未找到相关音乐，请尝试其他关键词")
                return False, "未找到音乐"

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 音乐搜索出错: {e}")
            await self.send_text(f"❌ 音乐搜索出错: {e}")
            return False, f"音乐搜索出错: {e}"

    async def _call_music_api(self, api_url: str, song_name: str, quality: str, timeout: int) -> Optional[dict]:
        """调用音乐API搜索歌曲"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                params = {
                    "word": song_name,
                    "quality": quality,
                    "choose": 1  # 选择第一首
                }

                async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            return data.get("data", {})
                        else:
                            logger.warning(f"{self.get_log_prefix()} API返回错误: {data.get('message', '未知错误')}")
                            return None
                    else:
                        logger.warning(f"{self.get_log_prefix()} API请求失败，状态码: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 调用音乐API出错: {e}")
            return None

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息"""
        try:
            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            quality = music_info.get("quality", "未知音质")
            interval = music_info.get("interval", "未知时长")
            cover = music_info.get("cover", "")
            link = music_info.get("link", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")

            # 构建消息内容
            message = f"🎵 找到音乐啦！\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"👤 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"🎧 音质：{quality}\n"
            message += f"⏱️ 时长：{interval}\n"

            if link:
                message += f"🔗 网易云链接：{link}\n"
            if url and self.get_config("features.show_download_link", False):
                message += f"⬇️ 下载链接：{url}\n"

            # 发送文本信息（可选）
            if self.get_config("features.show_info_text", True):
                await self.send_text(message)

            # 发送音乐 - 根据配置选择发送方式
            send_as_voice = self.get_config("features.send_as_voice", False)

            if send_as_voice:
                # 发送语音消息
                if url:
                    await self.send_custom(message_type="voiceurl", content=url)
                    logger.info(f"{self.get_log_prefix()} 发送语音消息成功，URL: {url[:50]}...")
                else:
                    logger.warning(f"{self.get_log_prefix()} 音乐URL为空，无法发送语音消息")
                    await self.send_text("❌ 无法获取音乐播放链接")
            else:
                # 发送音乐卡片
                if song_id:
                    await self.send_custom(message_type="music", content=song_id)
                    logger.info(f"{self.get_log_prefix()} 发送音乐卡片成功，ID: {song_id}")
                else:
                    logger.warning(f"{self.get_log_prefix()} 音乐ID为空，无法发送音乐卡片")

            # 发送封面图片
            if cover and self.get_config("features.show_cover", True):
                try:
                    timeout = self.get_config("api.timeout", 10)
                    response = requests.get(cover, timeout=timeout)
                    if response.status_code == 200:
                        base64_image = base64.b64encode(response.content).decode('utf-8')
                        await self.send_custom(message_type="image", content=base64_image)
                        logger.info(f"{self.get_log_prefix()} 发送封面成功")
                    else:
                        logger.warning(f"{self.get_log_prefix()} 获取封面失败，状态码: {response.status_code}")
                except Exception as e:
                    logger.warning(f"{self.get_log_prefix()} 发送封面失败: {e}")

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送音乐信息出错: {e}")
            await self.send_text("❌ 发送音乐信息时出现错误")

# ===== Command组件 =====

class MusicCommand(BaseCommand):
    """音乐点歌Command - 直接点歌命令"""

    command_name = "music"
    command_description = "点歌命令"
    command_pattern = r"^/music\s+(?P<song_name>.+)$"  # 用命名组
    command_help = "点歌命令，用法：/music 歌曲名"
    command_examples = ["/music 勾指起誓", "/music 晴天", "/music Jay Chou 青花瓷"]
    intercept_message = True

    def get_log_prefix(self) -> str:
        """获取日志前缀"""
        return f"[MusicCommand]"

    async def execute(self) -> Tuple[bool, str]:
        """执行音乐点歌命令"""
        try:
            # 获取匹配的参数
            song_name = (self.matched_groups or {}).get("song_name", "").strip()

            if not song_name:
                await self.send_text("❌ 请输入正确的格式：/music 歌曲名")
                return False, "缺少歌曲名称"

            # 从配置获取设置
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            quality = self.get_config("music.default_quality", "9")

            logger.info(f"{self.get_log_prefix()} 执行点歌命令，歌曲：{song_name[:50]}..., 音质：{quality}")

            # 调用音乐API
            music_info = await self._call_music_api(api_url, song_name, quality, timeout)

            if music_info:
                # 发送音乐信息
                await self._send_detailed_music_info(music_info)
                logger.info(f"{self.get_log_prefix()} 点歌成功")
                return True, f"成功点歌：{music_info.get('song', '未知')[:30]}..."
            else:
                await self.send_text("❌ 未找到相关音乐，请尝试其他关键词")
                return False, "未找到音乐"

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 点歌命令执行出错: {e}")
            await self.send_text(f"❌ 点歌失败: {e}")
            return False, f"点歌失败: {e}"

    async def _call_music_api(self, api_url: str, song_name: str, quality: str, timeout: int) -> Optional[dict]:
        """调用音乐API搜索歌曲"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                params = {
                    "word": song_name,
                    "quality": quality,
                    "choose": 1  # 选择第一首
                }

                async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            return data.get("data", {})
                        else:
                            logger.warning(f"{self.get_log_prefix()} API返回错误: {data.get('message', '未知错误')}")
                            return None
                    else:
                        logger.warning(f"{self.get_log_prefix()} API请求失败，状态码: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 调用音乐API出错: {e}")
            return None

    async def _send_detailed_music_info(self, music_info: dict):
        """发送详细音乐信息"""
        try:
            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            quality = music_info.get("quality", "未知音质")
            interval = music_info.get("interval", "未知时长")
            size = music_info.get("size", "未知大小")
            kbps = music_info.get("kbps", "未知码率")
            cover = music_info.get("cover", "")
            link = music_info.get("link", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")

            # 构建详细消息内容
            message = f"🎵 【点歌成功】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"
            message += f"🎯 音质：{quality}\n"
            message += f"📦 大小：{size}\n"
            message += f"📊 码率：{kbps}\n"

            if link:
                message += f"🔗 网易云链接：{link}\n"
            if url and self.get_config("features.show_download_link", False):
                message += f"⬇️ 下载链接：{url}\n"

            # 发送文本信息（可选）
            if self.get_config("features.show_info_text", True):
                await self.send_text(message)

            # 发送音乐 - 根据配置选择发送方式
            send_as_voice = self.get_config("features.send_as_voice", False)

            if send_as_voice:
                # 发送语音消息
                if url:
                    await self.send_type(message_type="voiceurl", content=url)
                    logger.info(f"{self.get_log_prefix()} 发送语音消息成功，URL: {url[:50]}...")
                else:
                    logger.warning(f"{self.get_log_prefix()} 音乐URL为空，无法发送语音消息")
                    await self.send_text("❌ 无法获取音乐播放链接")
            else:
                # 发送音乐卡片
                if song_id:
                    await self.send_type(message_type="music", content=song_id)
                    logger.info(f"{self.get_log_prefix()} 发送音乐卡片成功，ID: {song_id}")
                else:
                    logger.warning(f"{self.get_log_prefix()} 音乐ID为空，无法发送音乐卡片")

            # 发送封面图片
            if cover and self.get_config("features.show_cover", True):
                try:
                    timeout = self.get_config("api.timeout", 10)
                    response = requests.get(cover, timeout=timeout)
                    if response.status_code == 200:
                        base64_image = base64.b64encode(response.content).decode('utf-8')
                        await self.send_type(message_type="image", content=base64_image)
                        logger.info(f"{self.get_log_prefix()} 发送封面成功")
                    else:
                        logger.warning(f"{self.get_log_prefix()} 获取封面失败，状态码: {response.status_code}")
                except Exception as e:
                    logger.warning(f"{self.get_log_prefix()} 发送封面失败: {e}")

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送详细音乐信息出错: {e}")
            await self.send_text("❌ 发送音乐信息时出现错误")
# ===== 插件注册 =====

@register_plugin
class MusicPlugin(BasePlugin):
    """音乐点歌插件 - 基于网易云音乐API的智能点歌插件"""

    plugin_name = "music_plugin"
    plugin_description = "网易云音乐点歌插件，支持音乐搜索和点歌功能"
    plugin_version = "1.0.0"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []  # 插件依赖列表
    python_dependencies = ["aiohttp", "requests"]  # Python包依赖列表

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "api": "API接口配置",
        "music": "音乐功能配置",
        "features": "功能开关配置"
    }

    # 配置Schema
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件")
        },
        "components": {
            "action_enabled": ConfigField(type=bool, default=True, description="是否启用Action组件"),
            "command_enabled": ConfigField(type=bool, default=True, description="是否启用Command组件")
        },
        "api": {
            "base_url": ConfigField(
                type=str,
                default="https://api.vkeys.cn",
                description="音乐API基础URL"
            ),
            "timeout": ConfigField(type=int, default=10, description="API请求超时时间(秒)")
        },
        "music": {
            "default_quality": ConfigField(
                type=str,
                default="9",
                description="默认音质等级(1-9)"
            ),
            "max_search_results": ConfigField(
                type=int,
                default=10,
                description="最大搜索结果数"
            )
        },
        "features": {
            "show_cover": ConfigField(type=bool, default=True, description="是否显示专辑封面"),
            "show_download_link": ConfigField(
                type=bool,
                default=False,
                description="是否显示下载链接"
            ),
            "show_info_text": ConfigField(type=bool, default=True, description="是否显示音乐信息文本"),
            "send_as_voice": ConfigField(type=bool, default=False, description="是否以语音消息发送音乐（true=语音消息，false=音乐卡片）")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        components = []

        # 根据配置决定是否启用组件
        if self.get_config("components.action_enabled", True):
            components.append((MusicSearchAction.get_action_info(), MusicSearchAction))

        if self.get_config("components.command_enabled", True):
            components.append((MusicCommand.get_command_info(), MusicCommand))

        return components
