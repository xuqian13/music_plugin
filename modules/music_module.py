"""
音乐模块 - 网易云音乐点歌

基于网易云音乐和QQ音乐API的智能点歌插件
"""

import aiohttp
import asyncio
import time
from typing import Tuple, Optional, List, Any
from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool, ToolParamType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.apis import send_api
from ..utils.api_client import AsyncAPIClient
from ..utils.image_generator import generate_music_list_image, generate_music_list_text

logger = get_logger("entertainment_plugin.music")


# ===== 全局搜索缓存 =====
_search_cache = {}
_CACHE_TTL = 1800  # 30分钟


def get_search_cache(key: str) -> Optional[dict]:
    """获取搜索缓存"""
    if key in _search_cache:
        cache_data = _search_cache[key]
        if time.time() - cache_data.get("timestamp", 0) < _CACHE_TTL:
            return cache_data
        else:
            del _search_cache[key]
    return None


def set_search_cache(key: str, keyword: str, results: List[dict], source: str = "netease"):
    """设置搜索缓存"""
    _search_cache[key] = {
        "keyword": keyword,
        "results": results,
        "source": source,
        "timestamp": time.time()
    }


# ===== QuickChooseCommand 动态管理器 =====
_quick_choose_monitor_task = None
_quick_choose_enabled = False


def has_any_active_cache(timeout: int = 60) -> bool:
    """检查是否有任何活跃的搜索缓存

    Args:
        timeout: 快捷选择超时时间（秒）

    Returns:
        bool: 如果有任何缓存在超时时间内，返回 True
    """
    current_time = time.time()
    for cache_data in _search_cache.values():
        cache_timestamp = cache_data.get("timestamp", 0)
        if current_time - cache_timestamp < timeout:
            return True
    return False


async def _quick_choose_monitor(timeout: int = 60):
    """后台监控任务：定期检查缓存状态，自动禁用 QuickChooseCommand"""
    global _quick_choose_enabled, _quick_choose_monitor_task

    try:
        while True:
            await asyncio.sleep(5)  # 每5秒检查一次

            # 检查是否还有活跃缓存
            if not has_any_active_cache(timeout):
                # 所有缓存都过期了，禁用 QuickChooseCommand
                try:
                    from src.plugin_system.core.component_registry import component_registry
                    from src.plugin_system.base.component_types import ComponentType

                    await component_registry.disable_component("quick_choose", ComponentType.COMMAND)
                except Exception as disable_error:
                    # 忽略禁用时的错误（可能已经禁用或框架问题）
                    logger.debug(f"禁用快捷选择时出现错误（可忽略）: {disable_error}")

                _quick_choose_enabled = False
                logger.info("🔇 快捷选择已自动禁用（无活跃搜索）")

                # 停止监控任务
                _quick_choose_monitor_task = None
                break

    except asyncio.CancelledError:
        logger.debug("快捷选择监控任务被取消")
    except Exception as e:
        logger.error(f"快捷选择监控任务出错: {e}", exc_info=True)


async def enable_quick_choose_if_needed(timeout: int = 60):
    """如果 QuickChooseCommand 未启用，则启用它并启动监控任务

    Args:
        timeout: 快捷选择超时时间（秒）
    """
    global _quick_choose_enabled, _quick_choose_monitor_task

    if not _quick_choose_enabled:
        try:
            from src.plugin_system.core.component_registry import component_registry
            from src.plugin_system.base.component_types import ComponentType

            # 启用 QuickChooseCommand
            if component_registry.enable_component("quick_choose", ComponentType.COMMAND):
                _quick_choose_enabled = True
                logger.info("🔊 快捷选择已自动启用")
            else:
                logger.warning("启用快捷选择失败")
                return
        except Exception as e:
            logger.error(f"启用快捷选择时出错: {e}", exc_info=True)
            return

    # 启动或重启监控任务
    if _quick_choose_monitor_task is None or _quick_choose_monitor_task.done():
        _quick_choose_monitor_task = asyncio.create_task(_quick_choose_monitor(timeout))
        logger.debug("快捷选择监控任务已启动")


# ===== 音乐源适配器 =====

class MusicSourceAdapter:
    """音乐源适配器基类"""

    def __init__(self, api_url: str, timeout: int):
        self.api_url = api_url
        self.timeout = timeout
        self.source_name = "unknown"
        self.source_display_name = "未知"
        self.client = AsyncAPIClient(timeout)

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索音乐列表"""
        raise NotImplementedError

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取音乐详情"""
        raise NotImplementedError

    def normalize_music_info(self, data: dict) -> dict:
        """标准化音乐信息格式"""
        raise NotImplementedError


class NeteaseAdapter(MusicSourceAdapter):
    """网易云音乐适配器"""

    def __init__(self, api_url: str, timeout: int):
        super().__init__(api_url, timeout)
        self.source_name = "netease"
        self.source_display_name = "网易云音乐"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索网易云音乐列表"""
        try:
            params = {"word": keyword, "page": page, "num": num}
            data = await self.client.get_json(
                f"{self.api_url}/v2/music/netease",
                params=params,
                log_prefix="[Netease]"
            )
            if data and data.get("code") == 200:
                result_data = data.get("data", [])
                if isinstance(result_data, list) and len(result_data) > 0:
                    return [self.normalize_music_info(item) for item in result_data]
                elif isinstance(result_data, dict):
                    return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[NeteaseAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取网易云音乐详情"""
        try:
            params = {"word": keyword, "choose": choose}
            data = await self.client.get_json(
                f"{self.api_url}/v2/music/netease",
                params=params,
                log_prefix="[Netease]"
            )
            if data and data.get("code") == 200:
                result_data = data.get("data", {})
                if isinstance(result_data, list) and len(result_data) > 0:
                    result_data = result_data[0]
                if result_data and isinstance(result_data, dict):
                    return self.normalize_music_info(result_data)
        except Exception as e:
            logger.error(f"[NeteaseAdapter] 获取详情失败: {e}")
        return None

    def normalize_music_info(self, data: dict) -> dict:
        """标准化网易云音乐信息"""
        return {
            "source": self.source_name,
            "source_name": self.source_display_name,
            "id": data.get("id", ""),
            "song": data.get("song", "未知歌曲"),
            "singer": data.get("singer", "未知歌手"),
            "album": data.get("album", "未知专辑"),
            "cover": data.get("cover", ""),
            "url": data.get("url", ""),
            "link": data.get("link", ""),
            "interval": data.get("interval", "未知时长"),
            "size": data.get("size", "未知大小"),
            "quality": data.get("quality", "未知音质"),
        }


class QQMusicAdapter(MusicSourceAdapter):
    """QQ音乐适配器"""

    def __init__(self, api_url: str, timeout: int):
        super().__init__(api_url, timeout)
        self.source_name = "qq"
        self.source_display_name = "QQ音乐"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索QQ音乐列表"""
        try:
            params = {"word": keyword, "page": page, "num": num}
            data = await self.client.get_json(
                f"{self.api_url}/v2/music/tencent",
                params=params,
                log_prefix="[QQMusic]"
            )
            if data and data.get("code") == 200:
                result_data = data.get("data", [])
                if isinstance(result_data, list) and len(result_data) > 0:
                    return [self.normalize_music_info(item) for item in result_data]
                elif isinstance(result_data, dict):
                    return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[QQMusicAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取QQ音乐详情"""
        try:
            params = {"word": keyword, "choose": choose}
            data = await self.client.get_json(
                f"{self.api_url}/v2/music/tencent",
                params=params,
                log_prefix="[QQMusic]"
            )
            if data and data.get("code") == 200:
                result_data = data.get("data", {})
                if isinstance(result_data, list) and len(result_data) > 0:
                    result_data = result_data[0]
                if result_data and isinstance(result_data, dict):
                    return self.normalize_music_info(result_data)
        except Exception as e:
            logger.error(f"[QQMusicAdapter] 获取详情失败: {e}")
        return None

    def normalize_music_info(self, data: dict) -> dict:
        """标准化QQ音乐信息"""
        return {
            "source": self.source_name,
            "source_name": self.source_display_name,
            "id": data.get("id", "") or data.get("mid", ""),
            "song": data.get("song", "未知歌曲"),
            "singer": data.get("singer", "未知歌手"),
            "album": data.get("album", "未知专辑"),
            "cover": data.get("cover", ""),
            "url": data.get("url", ""),
            "link": data.get("link", ""),
            "interval": data.get("interval", "未知时长"),
            "size": data.get("size", "未知大小"),
            "quality": data.get("quality", "未知音质"),
        }


def get_music_adapter(source: str, api_url: str, timeout: int) -> MusicSourceAdapter:
    """获取音乐源适配器"""
    if source == "qq":
        return QQMusicAdapter(api_url, timeout)
    else:
        return NeteaseAdapter(api_url, timeout)


# ===== Command 组件 =====

class MusicCommand(BaseCommand):
    """音乐点歌 Command - 搜索音乐列表"""

    command_name = "music"
    command_description = "点歌命令"
    command_pattern = r"^/music\s+(?:(?P<source>netease|qq)\s+)?(?P<song_name>.+)$"
    command_help = "点歌命令，用法：/music [音源] 歌曲名"
    command_examples = ["/music 勾指起誓", "/music netease 晴天", "/music qq 青花瓷"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行音乐搜索命令"""
        try:
            song_name = ((self.matched_groups or {}).get("song_name") or "").strip()
            user_source = ((self.matched_groups or {}).get("source") or "").strip()

            if not song_name:
                await self.send_text("❌ 请输入正确的格式：/music [音源] 歌曲名\n可选音源：netease（网易云）、qq（QQ音乐）")
                return False, "缺少歌曲名称", True

            # 获取配置
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            timeout = self.get_config("music.timeout", 10)
            max_results = self.get_config("music.max_search_results", 10)
            default_source = self.get_config("music.default_source", "netease")

            # 确定搜索源
            if user_source:
                all_sources = [user_source]
            else:
                all_sources = ["netease", "qq"]
                if default_source in all_sources:
                    all_sources.remove(default_source)
                    all_sources.insert(0, default_source)

            # 尝试各个音源
            music_list = None
            successful_source = None
            adapter = None

            for source in all_sources:
                for attempt in range(1, 4):  # 每个源尝试3次
                    try:
                        adapter = get_music_adapter(source, api_url, timeout)
                        music_list = await adapter.search_list(song_name, page=1, num=max_results)

                        if music_list and len(music_list) > 0:
                            successful_source = source
                            logger.info(f"在 {source} 找到 {len(music_list)} 首歌曲")
                            break
                    except Exception as e:
                        logger.error(f"音乐源 {source} 第 {attempt} 次尝试出错: {e}")
                        if attempt < 3:
                            await asyncio.sleep(0.5)

                if music_list and len(music_list) > 0:
                    break

            if not music_list or len(music_list) == 0:
                await self.send_text("❌ 未找到相关音乐，请尝试其他关键词")
                return False, "未找到音乐", True

            # 保存搜索结果到缓存
            # 群聊：整个群共享搜索结果；私聊：每个用户独立缓存
            user_id = self.message.message_info.user_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'user_id') else "unknown"
            group_id = self.message.message_info.group_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'group_id') else None
            search_key = f"music_search_group_{group_id}" if group_id else f"music_search_user_{user_id}"

            set_search_cache(search_key, song_name, music_list, source=successful_source)
            logger.info(f"已保存 {len(music_list)} 个搜索结果到缓存: {search_key}")

            # 自动启用快捷选择功能
            quick_choose_timeout = self.get_config("music.quick_choose_timeout", 60)
            await enable_quick_choose_if_needed(quick_choose_timeout)

            # 发送列表（图片或文本）
            source_display_name = adapter.source_display_name if adapter else ""
            img_base64 = generate_music_list_image(music_list, song_name, source_display_name)

            if img_base64:
                await self.send_custom(message_type="image", content=img_base64)
            else:
                list_text = generate_music_list_text(music_list, song_name, source_display_name)
                await self.send_text(list_text)

            return True, f"搜索到 {len(music_list)} 首歌曲", True

        except Exception as e:
            logger.error(f"搜索命令执行出错: {e}", exc_info=True)
            await self.send_text(f"❌ 搜索失败: {str(e)}")
            return False, f"搜索失败: {e}", True


class ChooseCommand(BaseCommand):
    """选择歌曲 Command"""

    command_name = "choose"
    command_description = "从搜索结果中选择歌曲"
    command_pattern = r"^/choose\s+(?P<index>\d+)$"
    command_help = "选择歌曲命令，用法：/choose 序号"
    command_examples = ["/choose 1", "/choose 3"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行选择歌曲命令"""
        try:
            index_str = ((self.matched_groups or {}).get("index") or "").strip()
            if not index_str:
                await self.send_text("❌ 请输入正确的格式：/choose 序号")
                return False, "缺少序号", True

            index = int(index_str)

            # 获取缓存（群聊共享，私聊独立）
            user_id = self.message.message_info.user_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'user_id') else "unknown"
            group_id = self.message.message_info.group_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'group_id') else None
            search_key = f"music_search_group_{group_id}" if group_id else f"music_search_user_{user_id}"

            search_data = get_search_cache(search_key)
            if not search_data:
                await self.send_text("❌ 没有找到搜索记录，请先使用 /music 搜索歌曲")
                return False, "无搜索记录", True

            music_list = search_data.get("results", [])
            if index < 1 or index > len(music_list):
                await self.send_text(f"❌ 序号超出范围，请输入 1-{len(music_list)} 之间的数字")
                return False, "序号超出范围", True

            # 获取完整音乐信息
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            timeout = self.get_config("music.timeout", 10)
            keyword = search_data.get("keyword", "")
            source = search_data.get("source", "netease")

            adapter = get_music_adapter(source, api_url, timeout)
            music_info = await adapter.get_music_detail(keyword, index)

            if music_info:
                await self._send_music_info(music_info)
                return True, f"成功播放", True
            else:
                await self.send_text("❌ 获取歌曲详情失败，请重新搜索")
                return False, "获取歌曲详情失败", True

        except ValueError:
            await self.send_text("❌ 请输入有效的数字")
            return False, "序号格式错误", True
        except Exception as e:
            logger.error(f"选择命令执行出错: {e}", exc_info=True)
            await self.send_text(f"❌ 选择失败: {str(e)}")
            return False, f"选择失败: {e}", True

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息"""
        try:
            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            cover = music_info.get("cover", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")
            music_source = music_info.get("source", "netease")

            # 构建消息
            message = f"🎵 【正在播放】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"

            if self.get_config("music.show_info_text", True):
                await self.send_text(message)

            # 发送音乐
            send_as_voice = self.get_config("music.send_as_voice", False) or (music_source == "qq")

            if send_as_voice:
                if url:
                    await self.send_custom(message_type="voiceurl", content=url)
                else:
                    await self.send_text("❌ 无法获取音乐播放链接")
            else:
                if song_id:
                    await self.send_custom(message_type="music", content=song_id)

            # 发送封面
            if cover and self.get_config("music.show_cover", True):
                timeout = self.get_config("music.timeout", 10)
                client = AsyncAPIClient(timeout)
                base64_image = await client.download_image_base64(cover)
                if base64_image:
                    await self.send_custom(message_type="image", content=base64_image)

        except Exception as e:
            logger.error(f"发送音乐信息出错: {e}", exc_info=True)

    @classmethod
    def get_command_info(cls):
        """重写父类方法，返回默认禁用的 CommandInfo"""
        from src.plugin_system.base.component_types import CommandInfo, ComponentType

        return CommandInfo(
            name=cls.command_name,
            component_type=ComponentType.COMMAND,
            description=cls.command_description,
            command_pattern=cls.command_pattern,
            enabled=False  # 默认禁用，在有搜索缓存时动态启用
        )


class QuickChooseCommand(BaseCommand):
    """数字快捷选择 Command"""

    command_name = "quick_choose"
    command_description = "快捷选择歌曲（直接输入数字）"
    command_pattern = r"^(?P<index>\d+)$"
    command_help = "快捷选择歌曲，用法：直接输入数字 1-10"
    command_examples = ["1", "5", "10"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行快捷选择

        核心逻辑：只有在用户搜索音乐后的60秒内，才监听并处理数字消息
        其他时候直接不响应，让数字消息正常传递给其他功能
        """
        try:
            # 1. 检查是否启用快捷选择
            if not self.get_config("music.enable_quick_choose", True):
                return False, "", False

            # 2. 获取缓存 key（群聊共享，私聊独立）
            user_id = self.message.message_info.user_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'user_id') else "unknown"
            group_id = self.message.message_info.group_id if hasattr(self.message, 'message_info') and hasattr(self.message.message_info, 'group_id') else None
            search_key = f"music_search_group_{group_id}" if group_id else f"music_search_user_{user_id}"

            # 3. 检查是否有搜索缓存（最重要：没有搜索就不监听数字）
            search_data = get_search_cache(search_key)
            if not search_data:
                return False, "", False

            # 4. 检查缓存是否在有效期内（默认60秒）
            quick_choose_timeout = self.get_config("music.quick_choose_timeout", 60)
            cache_timestamp = search_data.get("timestamp", 0)
            time_elapsed = time.time() - cache_timestamp

            # 如果已超时，直接不响应，让消息继续传递
            if time_elapsed > quick_choose_timeout:
                return False, "", False

            # 5. 到这里说明有有效的搜索记录，开始解析数字
            index_str = ((self.matched_groups or {}).get("index") or "").strip()
            if not index_str:
                return False, "", False

            index = int(index_str)
            if index < 1 or index > 10:
                return False, "", False

            music_list = search_data.get("results", [])
            if index > len(music_list):
                await self.send_text(f"❌ 序号超出范围，当前列表只有 {len(music_list)} 首歌曲")
                return False, "序号超出范围", True

            # 获取音乐信息并播放（复用 ChooseCommand 逻辑）
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            timeout = self.get_config("music.timeout", 10)
            keyword = search_data.get("keyword", "")
            source = search_data.get("source", "netease")

            adapter = get_music_adapter(source, api_url, timeout)
            music_info = await adapter.get_music_detail(keyword, index)

            if music_info:
                # 直接发送音乐信息
                await self._send_music_info(music_info)
                return True, f"快捷播放成功", True
            else:
                await self.send_text("❌ 获取歌曲详情失败")
                return False, "获取歌曲详情失败", True

        except ValueError:
            return False, "数字格式错误", False
        except Exception as e:
            logger.error(f"快捷选择出错: {e}", exc_info=True)
            return False, f"快捷选择失败: {e}", False

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息"""
        try:
            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            cover = music_info.get("cover", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")
            music_source = music_info.get("source", "netease")

            # 构建消息
            message = f"🎵 【正在播放】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"

            if self.get_config("music.show_info_text", True):
                await self.send_text(message)

            # 发送音乐
            send_as_voice = self.get_config("music.send_as_voice", False) or (music_source == "qq")

            if send_as_voice:
                if url:
                    await self.send_custom(message_type="voiceurl", content=url)
                else:
                    await self.send_text("❌ 无法获取音乐播放链接")
            else:
                if song_id:
                    await self.send_custom(message_type="music", content=song_id)

            # 发送封面
            if cover and self.get_config("music.show_cover", True):
                timeout = self.get_config("music.timeout", 10)
                client = AsyncAPIClient(timeout)
                base64_image = await client.download_image_base64(cover)
                if base64_image:
                    await self.send_custom(message_type="image", content=base64_image)

        except Exception as e:
            logger.error(f"发送音乐信息出错: {e}", exc_info=True)

    @classmethod
    def get_command_info(cls):
        """重写父类方法，返回默认禁用的 CommandInfo"""
        from src.plugin_system.base.component_types import CommandInfo, ComponentType

        return CommandInfo(
            name=cls.command_name,
            component_type=ComponentType.COMMAND,
            description=cls.command_description,
            command_pattern=cls.command_pattern,
            enabled=False  # 默认禁用，在有搜索缓存时动态启用
        )

# ===== Tool 组件 =====

class PlayMusicTool(BaseTool):
    """播放音乐 Tool - 供AI主动调用"""

    name = "play_music"
    description = "搜索并播放歌曲。重要：调用此工具时必须提供具体歌名。如果用户没指定歌名（如'推首歌'），AI应该根据聊天上下文、用户情绪、喜好等自行推荐一首合适的歌曲，然后将歌名作为参数传给此工具"
    parameters = [
        ("song_name", ToolParamType.STRING, "歌曲名称或歌手+歌名，必填。AI需要填写具体歌名，不能为空", True, None),
        ("source", ToolParamType.STRING, "音乐源，可选netease(网易云)或qq(QQ音乐)，默认netease", False, ["netease", "qq"])
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行音乐播放"""
        try:
            song_name = function_args.get("song_name", "").strip()
            user_source = function_args.get("source", "").strip()

            # 如果歌名为空，使用默认热门歌曲列表随机选一首
            if not song_name:
                import random
                default_songs = [
                    "水星记", "起风了", "光年之外", "稻香", "晴天",
                    "告白气球", "青花瓷", "七里香", "遇见", "演员"
                ]
                song_name = random.choice(default_songs)
                logger.info(f"[PlayMusicTool] 用户未指定歌名，自动推荐: {song_name}")

            # 获取配置
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            timeout = self.get_config("music.timeout", 10)
            default_source = self.get_config("music.default_source", "netease")

            # 确定搜索源
            if user_source:
                all_sources = [user_source]
            else:
                all_sources = ["netease", "qq"]
                if default_source in all_sources:
                    all_sources.remove(default_source)
                    all_sources.insert(0, default_source)

            # 尝试各个音源搜索
            music_info = None
            successful_source = None

            for source in all_sources:
                for attempt in range(1, 4):  # 每个源尝试3次
                    try:
                        adapter = get_music_adapter(source, api_url, timeout)
                        music_list = await adapter.search_list(song_name, page=1, num=1)

                        if music_list and len(music_list) > 0:
                            # 获取第一首歌的详细信息
                            music_info = await adapter.get_music_detail(song_name, 1)
                            if music_info:
                                successful_source = source
                                logger.info(f"[PlayMusicTool] 在 {source} 找到歌曲: {music_info.get('song')}")
                                break
                    except Exception as e:
                        logger.error(f"[PlayMusicTool] 音乐源 {source} 第 {attempt} 次尝试出错: {e}")
                        if attempt < 3:
                            await asyncio.sleep(0.5)

                if music_info:
                    break

            if not music_info:
                return {"name": self.name, "content": f"❌ 未找到歌曲《{song_name}》，请尝试其他关键词或歌手名"}

            # 发送音乐信息和播放
            await self._send_music_to_chat(music_info)

            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            source_name = music_info.get("source_name", "")

            return {
                "name": self.name,
                "content": f"✅ 已为你播放《{song}》- {singer} (来源: {source_name})"
            }

        except Exception as e:
            logger.error(f"[PlayMusicTool] 播放音乐出错: {e}", exc_info=True)
            return {"name": self.name, "content": f"❌ 播放失败: {str(e)}"}

    async def _send_music_to_chat(self, music_info: dict):
        """发送音乐到聊天流"""
        try:
            if not self.chat_stream:
                logger.error("[PlayMusicTool] chat_stream 未初始化")
                return

            stream_id = self.chat_stream.stream_id
            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            cover = music_info.get("cover", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")
            music_source = music_info.get("source", "netease")

            # 构建消息
            message = f"🎵 【正在播放】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"

            # 发送文本信息
            if self.get_config("music.show_info_text", True):
                await send_api.text_to_stream(message, stream_id)

            # 发送音乐卡片或语音
            send_as_voice = self.get_config("music.send_as_voice", False) or (music_source == "qq")

            if send_as_voice:
                if url:
                    await send_api.custom_to_stream("voiceurl", url, stream_id)
                else:
                    logger.warning("[PlayMusicTool] 无法获取音乐播放链接")
            else:
                if song_id:
                    await send_api.custom_to_stream("music", song_id, stream_id)

            # 发送封面
            if cover and self.get_config("music.show_cover", True):
                timeout = self.get_config("music.timeout", 10)
                client = AsyncAPIClient(timeout)
                base64_image = await client.download_image_base64(cover)
                if base64_image:
                    await send_api.custom_to_stream("image", base64_image, stream_id)

            logger.info(f"[PlayMusicTool] 已发送音乐《{song}》到聊天流 {stream_id}")

        except Exception as e:
            logger.error(f"[PlayMusicTool] 发送音乐信息出错: {e}", exc_info=True)
