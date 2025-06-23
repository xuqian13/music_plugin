from typing import List, Tuple, Type
import aiohttp
import json
from src.plugin_system.apis import send_api, chat_api
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ChatMode
)
from src.plugin_system.base.config_types import ConfigField
from src.common.logger import get_logger

logger = get_logger("music")

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
    
    activation_keywords = ["音乐", "歌曲", "点歌", "听歌", "music", "song"]
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

    async def execute(self) -> Tuple[bool, str]:
        """执行音乐搜索"""
        song_name = self.action_data.get("song_name", "")
        quality = self.action_data.get("quality", "9")  # 默认最高音质
        
        if not song_name:
            await self.send_text("请告诉我你想听什么歌曲~")
            return True, "请求用户输入歌曲名"

        try:
            # 调用音乐API
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            async with aiohttp.ClientSession() as session:
                params = {
                    "word": song_name,
                    "quality": quality,
                    "choose": 1  # 选择第一首
                }
                
                async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            music_info = data.get("data", {})
                            await self._send_music_info(music_info)
                            return True, f"找到音乐: {music_info.get('song', '未知')}"
                        else:
                            await self.send_text(f"搜索失败: {data.get('message', '未知错误')}")
                            return False, "API返回错误"
                    else:
                        await self.send_text("音乐服务暂时不可用，请稍后再试")
                        return False, "API请求失败"
                        
        except Exception as e:
            logger.error(f"音乐搜索失败: {e}")
            await self.send_text("搜索音乐时出现错误，请稍后再试")
            return False, f"搜索失败: {str(e)}"

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息"""
        song = music_info.get("song", "未知歌曲")
        singer = music_info.get("singer", "未知歌手")
        album = music_info.get("album", "未知专辑")
        quality = music_info.get("quality", "未知音质")
        interval = music_info.get("interval", "未知时长")
        cover = music_info.get("cover", "")
        url = music_info.get("url", "")
        
        message = f"🎵 找到音乐啦！\n\n"
        message += f"歌曲：{song}\n"
        message += f"歌手：{singer}\n"
        message += f"专辑：{album}\n"
        message += f"音质：{quality}\n"
        message += f"时长：{interval}\n"
        
        if url and self.get_config("features.show_download_link", False):
            message += f"\n🔗 播放链接：{url}"
            
        await self.send_text(message)
        await self.send_custom(message_type="voiceurl", content=url)
        # 如果有封面图片，可以发送图片
        if cover and self.get_config("features.show_cover", True):
            try:
                await self.send_image_url(cover)
            except Exception as e:
                logger.warning(f"发送封面失败: {e}")

# ===== Command组件 =====

class MusicCommand(BaseCommand):
    """音乐点歌Command - 直接点歌命令"""

    command_name = "music"
    command_description = "点歌命令"
    command_pattern = r"^/music\s+(?P<song_name>.+)$"  # 用命名组
    command_help = "点歌命令，用法：/music 歌曲名"
    command_examples = ["/music 勾指起誓", "/music 晴天"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str]:
        # 只在标准 Action 场景下用，直接依赖 self.chat_stream
        song_name = (self.matched_groups or {}).get("song_name", "")
        if not song_name:
            await self.send_text("请输入正确的格式：/music 歌曲名")
            return False, "格式错误"
        try:
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            quality = self.get_config("music.default_quality", "9")
            async with aiohttp.ClientSession() as session:
                params = {
                    "word": song_name,
                    "quality": quality,
                    "choose": 1
                }
                async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            music_info = data.get("data", {})
                            await self._send_detailed_music_info(music_info)
                            return True, f"点歌成功: {music_info.get('song', '未知')}"
                        else:
                            await self.send_text(f"❌ 搜索失败: {data.get('message', '未知错误')}")
                            return False, "搜索失败"
                    else:
                        await self.send_text("❌ 音乐服务不可用")
                        return False, "服务不可用"
        except Exception as e:
            logger.error(f"点歌失败: {e}")
            await self.send_text(f"❌ 点歌失败，请稍后再试\n错误信息: {e}")
            return False, f"点歌失败: {str(e)}"

    async def _send_detailed_music_info(self, music_info: dict):
        """发送详细音乐信息，仅用 send_custom 发送 voiceurl"""
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
        await self.send_text(message)
        if url:
            await self.send_custom(message_type="voiceurl", content=url)

    async def send_custom(self, message_type, content):
        """兼容Action的send_custom，Command场景下优先用self.chat_stream，兜底用self.message.chat_stream"""
        chat_stream = getattr(self, "chat_stream", None)
        if chat_stream is None and hasattr(self, "message") and hasattr(self.message, "chat_stream"):
            chat_stream = self.message.chat_stream
        if chat_stream is None:
            await self.send_text("❌ chat_stream 未注入，无法发送自定义消息")
            return
        await smart_send(chat_stream, {"type": message_type, "content": content})

# ===== 插件注册 =====

@register_plugin
class MusicPlugin(BasePlugin):
    """音乐点歌插件"""

    plugin_name = "music_plugin"
    plugin_description = "网易云音乐点歌插件，支持音乐搜索和点歌功能"
    plugin_version = "1.0.0"
    plugin_author = "靓仔"
    enable_plugin = True
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "api": "API接口配置", 
        "music": "音乐功能配置",
        "features": "功能开关配置"
    }

    # 配置Schema
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件")
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
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        return [
            (MusicSearchAction.get_action_info(), MusicSearchAction),
            (MusicCommand.get_command_info(), MusicCommand),
        ]
