"""
音乐模块 - 网易云音乐点歌

基于网易云音乐和QQ音乐API的智能点歌插件

功能：
- 支持多音源：网易云、QQ音乐、聚合点歌、VIP音质
- 智能搜索和选择
- 数字快捷选择
- 自动缓存管理
"""

import aiohttp
import asyncio
import time
from typing import Tuple, Optional, List, Any, Dict
from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool, ToolParamType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.apis import send_api
from ..utils.api_client import AsyncAPIClient
from ..utils.image_generator import generate_music_list_image, generate_music_list_text

logger = get_logger("entertainment_plugin.music")


# ===== 全局搜索缓存 =====
_search_cache: Dict[str, dict] = {}
_search_cache_lock = asyncio.Lock()  # 缓存并发保护
_CACHE_TTL = 1800  # 30分钟
_cache_cleanup_task: Optional[asyncio.Task] = None


async def get_search_cache(key: str) -> Optional[dict]:
    """
    获取搜索缓存（线程安全，自动过期检查）

    特性：
    - 使用asyncio.Lock确保并发访问安全
    - 自动检查缓存是否过期（TTL=30分钟）
    - 过期缓存自动删除

    Args:
        key: 缓存键（通常是chat_id，如"music_search_group_123"或"music_search_user_456"）

    Returns:
        缓存数据字典或None（如果不存在或已过期）
        - keyword: 搜索关键词
        - results: 搜索结果列表
        - source: 音乐源
        - timestamp: 缓存时间戳
    """
    async with _search_cache_lock:
        if key in _search_cache:
            cache_data = _search_cache[key]
            if time.time() - cache_data.get("timestamp", 0) < _CACHE_TTL:
                return cache_data
            else:
                # 过期，删除缓存
                del _search_cache[key]
                logger.debug(f"缓存已过期并删除: {key}")
        return None


async def set_search_cache(key: str, keyword: str, results: List[dict], source: str = "netease"):
    """
    设置搜索缓存（线程安全）

    特性：
    - 使用asyncio.Lock确保并发写入安全
    - 自动记录时间戳用于TTL检查
    - 支持多音乐源缓存

    Args:
        key: 缓存键（如"music_search_group_123"）
        keyword: 搜索关键词（如"晴天"）
        results: 搜索结果列表（包含歌曲信息的字典列表）
        source: 音乐源（netease/qq/netease_vip/qq_vip/juhe）
    """
    async with _search_cache_lock:
        _search_cache[key] = {
            "keyword": keyword,
            "results": results,
            "source": source,
            "timestamp": time.time()
        }
        logger.debug(f"缓存已设置: {key}, 关键词={keyword}, 结果数={len(results)}")


async def _cleanup_expired_cache():
    """后台任务：定期清理过期缓存"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟检查一次

            async with _search_cache_lock:
                current_time = time.time()
                expired_keys = [
                    key for key, data in _search_cache.items()
                    if current_time - data.get("timestamp", 0) >= _CACHE_TTL
                ]

                for key in expired_keys:
                    del _search_cache[key]

                if expired_keys:
                    logger.info(f"清理了 {len(expired_keys)} 个过期缓存")

        except asyncio.CancelledError:
            logger.debug("缓存清理任务被取消")
            break
        except Exception as e:
            logger.error(f"缓存清理任务出错: {e}", exc_info=True)


def start_cache_cleanup():
    """启动缓存清理任务"""
    global _cache_cleanup_task
    if _cache_cleanup_task is None or _cache_cleanup_task.done():
        _cache_cleanup_task = asyncio.create_task(_cleanup_expired_cache())
        logger.info("缓存清理任务已启动")


# ===== 公共音乐发送函数 =====

async def send_music_info_to_command(
    component,
    music_info: dict,
    config_getter: callable
):
    """
    发送音乐信息到聊天（Command组件使用）

    功能说明：
    - 发送音乐信息文本（歌名、歌手、专辑、时长）
    - 发送音乐卡片或语音消息（根据配置）
    - 发送专辑封面图片（可选）
    - 自动处理QQ音乐的语音模式

    Args:
        component: Command组件实例（需要有send_text、send_custom方法）
        music_info: 音乐信息字典，包含：
            - song: 歌曲名
            - singer: 歌手
            - album: 专辑名
            - interval: 时长
            - cover: 封面URL
            - url: 播放链接
            - id: 歌曲ID
            - source: 音乐源（netease/qq/juhe等）
        config_getter: 配置获取函数（如self.get_config）
    """
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

        # 发送文本信息
        if config_getter("music.show_info_text", True):
            await component.send_text(message)

        # 发送音乐卡片或语音
        send_as_voice = config_getter("music.send_as_voice", False) or (music_source == "qq")

        if send_as_voice:
            if url:
                await component.send_custom(message_type="voiceurl", content=url)
            else:
                await component.send_text("❌ 无法获取音乐播放链接")
        else:
            if song_id:
                await component.send_custom(message_type="music", content=song_id)

        # 发送封面
        if cover and config_getter("music.show_cover", True):
            timeout = config_getter("music.timeout", 10)
            client = AsyncAPIClient(timeout)
            base64_image = await client.download_image_base64(cover)
            if base64_image:
                await component.send_custom(message_type="image", content=base64_image)

        logger.info(f"成功发送音乐《{song}》by {singer}")

    except Exception as e:
        logger.error(f"发送音乐信息出错: {e}", exc_info=True)


async def send_music_info_to_stream(
    stream_id: str,
    music_info: dict,
    config_getter: callable
):
    """
    发送音乐信息到聊天流（Tool组件使用）

    功能说明：
    - 发送音乐信息文本（歌名、歌手、专辑、时长）
    - 发送音乐卡片或语音消息（根据配置）
    - 发送专辑封面图片（可选）
    - 自动处理QQ音乐的语音模式

    Args:
        stream_id: 聊天流ID（用于send_api调用）
        music_info: 音乐信息字典，包含：
            - song: 歌曲名
            - singer: 歌手
            - album: 专辑名
            - interval: 时长
            - cover: 封面URL
            - url: 播放链接
            - id: 歌曲ID
            - source: 音乐源（netease/qq/juhe等）
        config_getter: 配置获取函数（如self.get_config）
    """
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

        # 发送文本信息
        if config_getter("music.show_info_text", True):
            await send_api.text_to_stream(message, stream_id)

        # 发送音乐卡片或语音
        send_as_voice = config_getter("music.send_as_voice", False) or (music_source == "qq")

        if send_as_voice:
            if url:
                await send_api.custom_to_stream("voiceurl", url, stream_id)
            else:
                logger.warning("无法获取音乐播放链接")
        else:
            if song_id:
                await send_api.custom_to_stream("music", song_id, stream_id)

        # 发送封面
        if cover and config_getter("music.show_cover", True):
            timeout = config_getter("music.timeout", 10)
            client = AsyncAPIClient(timeout)
            base64_image = await client.download_image_base64(cover)
            if base64_image:
                await send_api.custom_to_stream("image", base64_image, stream_id)

        logger.info(f"成功发送音乐《{song}》到聊天流 {stream_id}")

    except Exception as e:
        logger.error(f"发送音乐信息到流出错: {e}", exc_info=True)


# ===== 快捷选择辅助函数（已简化）=====

async def is_quick_choose_valid(chat_id: str, timeout: int = 60) -> bool:
    """
    检查快捷选择是否有效（缓存是否在超时时间内）

    Args:
        chat_id: 聊天ID
        timeout: 快捷选择超时时间（秒）

    Returns:
        bool: 是否有效
    """
    cache = await get_search_cache(chat_id)
    if not cache:
        return False

    # 检查缓存是否在快捷选择超时时间内
    cache_age = time.time() - cache.get("timestamp", 0)
    return cache_age < timeout


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


class NeteaseVIPAdapter(MusicSourceAdapter):
    """网易云音乐VIP适配器"""

    def __init__(self, vip_api_url: str, timeout: int):
        # 拼接完整的API路径
        full_api_url = vip_api_url.rstrip('/') + '/netmusic'
        super().__init__(full_api_url, timeout)
        self.source_name = "netease_vip"
        self.source_display_name = "网易云音乐VIP"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索网易云音乐VIP列表"""
        try:
            # 限制返回数量在1-100之间
            limit = min(max(num, 1), 100)
            params = {"name": keyword, "limit": limit}

            data = await self.client.get_json(
                self.api_url,
                params=params,
                log_prefix="[NeteaseVIP]"
            )

            # 根据API文档,返回格式可能是列表或对象
            if data:
                # 如果返回是列表,直接使用
                if isinstance(data, list):
                    return [self.normalize_music_info(item) for item in data[:limit]]
                # 如果返回是字典,可能包含data字段
                elif isinstance(data, dict):
                    result_data = data.get("data", data)
                    if isinstance(result_data, list):
                        return [self.normalize_music_info(item) for item in result_data[:limit]]
                    else:
                        return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[NeteaseVIPAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取网易云音乐VIP详情

        Args:
            keyword: 搜索关键词
            choose: 选择第几首歌(从1开始)
        """
        try:
            # 先搜索歌曲列表
            music_list = await self.search_list(keyword, page=1, num=choose)

            if not music_list or len(music_list) < choose:
                logger.error(f"[NeteaseVIPAdapter] 搜索结果不足,需要第{choose}首,实际只有{len(music_list) if music_list else 0}首")
                return None

            # 从列表中获取指定序号的歌曲
            selected_music = music_list[choose - 1]  # choose从1开始,列表从0开始

            # 如果有mid,使用mid获取高音质链接
            mid = selected_music.get("mid") or selected_music.get("id")
            if mid:
                # 使用mid获取VIP音质的播放链接
                params = {"mid": mid, "level": 2}  # level=2是建议的最低音质

                data = await self.client.get_json(
                    self.api_url,
                    params=params,
                    log_prefix="[NeteaseVIP]"
                )

                if data:
                    # VIP API返回格式: {"data": {...}, "retcode": 0}
                    if isinstance(data, dict):
                        # 提取data字段
                        vip_data = data.get("data", data)
                        url = vip_data.get("url") or vip_data.get("mp3")
                        if url:
                            selected_music["url"] = url
                            selected_music["quality"] = "VIP音质"
                            # 更新其他信息
                            if vip_data.get("size"):
                                selected_music["size"] = vip_data.get("size")
                            if vip_data.get("level"):
                                selected_music["quality"] = f"VIP音质({vip_data.get('level')})"

            return selected_music

        except Exception as e:
            logger.error(f"[NeteaseVIPAdapter] 获取详情失败: {e}")
        return None

    def normalize_music_info(self, data: dict) -> dict:
        """标准化网易云音乐VIP信息"""
        return {
            "source": self.source_name,
            "source_name": self.source_display_name,
            "id": data.get("id", "") or data.get("mid", ""),
            "mid": data.get("mid", ""),
            "song": data.get("song", "") or data.get("name", "未知歌曲"),
            "singer": data.get("singer", "") or data.get("artist", "未知歌手"),
            "album": data.get("album", "未知专辑"),
            "cover": data.get("cover", "") or data.get("pic", ""),
            "url": data.get("url", "") or data.get("mp3", ""),
            "link": data.get("link", ""),
            "interval": data.get("interval", "") or data.get("time", "未知时长"),
            "size": data.get("size", "未知大小"),
            "quality": data.get("quality", "") or data.get("level", "VIP音质"),
        }


class QQMusicVIPAdapter(MusicSourceAdapter):
    """QQ音乐VIP适配器"""

    def __init__(self, vip_api_url: str, timeout: int):
        # 拼接完整的API路径
        full_api_url = vip_api_url.rstrip('/') + '/qqmusic'
        super().__init__(full_api_url, timeout)
        self.source_name = "qq_vip"
        self.source_display_name = "QQ音乐VIP"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索QQ音乐VIP列表"""
        try:
            # 限制返回数量在1-100之间
            limit = min(max(num, 1), 100)
            params = {"name": keyword, "limit": limit}

            data = await self.client.get_json(
                self.api_url,
                params=params,
                log_prefix="[QQMusicVIP]"
            )

            # 根据API文档,返回格式可能是列表或对象
            if data:
                # 如果返回是列表,直接使用
                if isinstance(data, list):
                    return [self.normalize_music_info(item) for item in data[:limit]]
                # 如果返回是字典,可能包含data字段
                elif isinstance(data, dict):
                    result_data = data.get("data", data)
                    if isinstance(result_data, list):
                        return [self.normalize_music_info(item) for item in result_data[:limit]]
                    else:
                        return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[QQMusicVIPAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取QQ音乐VIP详情

        Args:
            keyword: 搜索关键词
            choose: 选择第几首歌(从1开始)
        """
        try:
            # 先搜索歌曲列表
            music_list = await self.search_list(keyword, page=1, num=choose)

            if not music_list or len(music_list) < choose:
                logger.error(f"[QQMusicVIPAdapter] 搜索结果不足,需要第{choose}首,实际只有{len(music_list) if music_list else 0}首")
                return None

            # 从列表中获取指定序号的歌曲
            selected_music = music_list[choose - 1]  # choose从1开始,列表从0开始

            # 如果有mid,使用mid获取高音质链接
            mid = selected_music.get("mid") or selected_music.get("id")
            if mid:
                # 使用mid获取VIP音质的播放链接
                params = {"mid": mid, "quality": 2}  # quality=2

                data = await self.client.get_json(
                    self.api_url,
                    params=params,
                    log_prefix="[QQMusicVIP]"
                )

                if data:
                    # VIP API返回格式: {"data": {...}, "retcode": 0}
                    if isinstance(data, dict):
                        # 提取data字段
                        vip_data = data.get("data", data)
                        url = vip_data.get("url") or vip_data.get("mp3")
                        if url:
                            selected_music["url"] = url
                            selected_music["quality"] = "VIP音质"
                            # 更新其他信息
                            if vip_data.get("size"):
                                selected_music["size"] = vip_data.get("size")
                            if vip_data.get("level"):
                                selected_music["quality"] = f"VIP音质({vip_data.get('level')})"

            return selected_music

        except Exception as e:
            logger.error(f"[QQMusicVIPAdapter] 获取详情失败: {e}")
        return None

    def normalize_music_info(self, data: dict) -> dict:
        """标准化QQ音乐VIP信息"""
        return {
            "source": self.source_name,
            "source_name": self.source_display_name,
            "id": data.get("id", "") or data.get("mid", ""),
            "mid": data.get("mid", ""),
            "song": data.get("song", "") or data.get("name", "未知歌曲"),
            "singer": data.get("singer", "") or data.get("artist", "未知歌手"),
            "album": data.get("album", "未知专辑"),
            "cover": data.get("cover", "") or data.get("pic", ""),
            "url": data.get("url", "") or data.get("mp3", ""),
            "link": data.get("link", ""),
            "interval": data.get("interval", "") or data.get("time", "未知时长"),
            "size": data.get("size", "未知大小"),
            "quality": data.get("quality", "") or data.get("level", "VIP音质"),
        }


class JuheAdapter(MusicSourceAdapter):
    """聚合点歌适配器"""

    def __init__(self, api_url: str, timeout: int):
        super().__init__(api_url, timeout)
        self.source_name = "juhe"
        self.source_display_name = "聚合点歌"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索聚合点歌列表"""
        try:
            # 不使用n参数,API会返回多首歌曲列表
            params = {"msg": keyword, "type": "json"}
            data = await self.client.get_json(
                self.api_url,
                params=params,
                log_prefix="[Juhe]"
            )

            # 聚合API返回格式: {"list": [...]}
            if data and isinstance(data, dict):
                result_list = data.get("list")

                if isinstance(result_list, list) and len(result_list) > 0:
                    # 限制返回数量
                    music_list = [self.normalize_music_info(item, i) for i, item in enumerate(result_list[:num])]
                    return music_list

            # 如果data直接是列表
            elif isinstance(data, list) and len(data) > 0:
                music_list = [self.normalize_music_info(item, i) for i, item in enumerate(data[:num])]
                return music_list

        except Exception as e:
            logger.error(f"[JuheAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int) -> Optional[dict]:
        """获取聚合点歌详情

        Args:
            keyword: 搜索关键词
            choose: 选择第几首歌(从1开始)

        返回格式: {"data": {"code": 200, "title": "...", "url": "...", ...}}
        """
        try:
            params = {"msg": keyword, "n": choose, "type": "json"}
            response = await self.client.get_json(
                self.api_url,
                params=params,
                log_prefix="[Juhe]"
            )

            if response and isinstance(response, dict):
                # 提取data字段
                data = response.get("data")

                if data and data.get("code") == 200:
                    # 标准化音乐信息
                    return {
                        "source": self.source_name,
                        "source_name": self.source_display_name,
                        "id": str(data.get("selected_index") or choose),
                        "song": data.get("title") or "未知歌曲",
                        "singer": data.get("singer") or "未知歌手",
                        "album": "未知专辑",
                        "cover": data.get("cover") or "",
                        "url": data.get("url") or "",
                        "link": data.get("link") or "",
                        "interval": "未知时长",
                        "size": "未知大小",
                        "quality": "聚合音质",
                    }

        except Exception as e:
            logger.error(f"[JuheAdapter] 获取详情失败: {e}")
        return None

    def normalize_music_info(self, data: dict, index: int = 0) -> dict:
        """标准化聚合点歌信息

        Args:
            data: API返回的歌曲数据
            index: 歌曲在列表中的索引(用于生成ID)

        API返回字段: n, title, singer, app, songid, cover, has_accompaniment
        """
        # 使用API提供的songid或n作为ID
        song_id = data.get("songid") or data.get("n") or str(index + 1)

        return {
            "source": self.source_name,
            "source_name": self.source_display_name,
            "id": str(song_id),
            "song": data.get("title") or "未知歌曲",
            "singer": data.get("singer") or "未知歌手",
            "album": "未知专辑",
            "cover": data.get("cover") or "",
            "url": data.get("url") or "",  # 列表中不包含url,需要在get_music_detail中获取
            "link": data.get("link") or "",
            "interval": data.get("time") or "未知时长",
            "size": "未知大小",
            "quality": f"聚合音质({data.get('app', 'unknown')})",
            # 保存原始数据用于后续获取详情
            "_raw_n": data.get("n"),
            "_raw_app": data.get("app"),
        }


def get_music_adapter(source: str, api_url: str, timeout: int, vip_api_url: str = None, juhe_api_url: str = None) -> MusicSourceAdapter:
    """获取音乐源适配器

    Args:
        source: 音乐源(netease/qq/netease_vip/qq_vip/juhe)
        api_url: 普通API地址
        timeout: 超时时间
        vip_api_url: VIP API地址
        juhe_api_url: 聚合点歌API地址
    """
    if source == "qq":
        return QQMusicAdapter(api_url, timeout)
    elif source == "qq_vip":
        return QQMusicVIPAdapter(vip_api_url or "https://www.littleyouzi.com/api/v2/qqmusic", timeout)
    elif source == "netease_vip":
        return NeteaseVIPAdapter(vip_api_url or "https://www.littleyouzi.com/api/v2/netmusic", timeout)
    elif source == "juhe":
        return JuheAdapter(juhe_api_url or "https://api.xcvts.cn/api/music/juhe", timeout)
    else:
        return NeteaseAdapter(api_url, timeout)


# ===== Command 组件 =====

class MusicCommand(BaseCommand):
    """音乐点歌 Command - 搜索音乐列表"""

    command_name = "music"
    command_description = "点歌命令"
    command_pattern = r"^/music\s+(?:(?P<source>netease|qq|netease_vip|qq_vip|juhe)\s+)?(?P<song_name>.+)$"
    command_help = "点歌命令，用法：/music [音源] 歌曲名"
    command_examples = [
        "/music 勾指起誓",
        "/music netease 晴天",
        "/music qq 青花瓷",
        "/music netease_vip 稻香",
        "/music qq_vip 七里香",
        "/music juhe 起风了"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行音乐搜索命令"""
        try:
            song_name = ((self.matched_groups or {}).get("song_name") or "").strip()
            user_source = ((self.matched_groups or {}).get("source") or "").strip()

            if not song_name:
                await self.send_text(
                    "❌ 请输入正确的格式：/music [音源] 歌曲名\n"
                    "可选音源：\n"
                    "- netease（网易云）\n"
                    "- qq（QQ音乐）\n"
                    "- netease_vip（网易云VIP）\n"
                    "- qq_vip（QQ音乐VIP）\n"
                    "- juhe（聚合点歌）"
                )
                return False, "缺少歌曲名称", True

            # 获取配置
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            vip_api_url = self.get_config("music.vip_api_url", "https://www.littleyouzi.com/api/v2")
            juhe_api_url = self.get_config("music.juhe_api_url", "https://api.xcvts.cn/api/music/juhe")
            timeout = self.get_config("music.timeout", 10)
            max_results = self.get_config("music.max_search_results", 10)
            default_source = self.get_config("music.default_source", "netease")

            # 确定搜索源
            if user_source:
                all_sources = [user_source]
            else:
                all_sources = ["netease", "qq", "netease_vip", "qq_vip", "juhe"]
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
                        # 根据源类型选择合适的API URL
                        if source in ["netease_vip", "qq_vip"]:
                            adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)
                        elif source == "juhe":
                            adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)
                        else:
                            adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)

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

            await set_search_cache(search_key, song_name, music_list, source=successful_source)
            logger.info(f"已保存 {len(music_list)} 个搜索结果到缓存: {search_key}")

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

            search_data = await get_search_cache(search_key)
            if not search_data:
                await self.send_text("❌ 没有找到搜索记录，请先使用 /music 搜索歌曲")
                return False, "无搜索记录", True

            music_list = search_data.get("results", [])
            if index < 1 or index > len(music_list):
                await self.send_text(f"❌ 序号超出范围，请输入 1-{len(music_list)} 之间的数字")
                return False, "序号超出范围", True

            # 获取完整音乐信息
            api_url = self.get_config("music.api_url", "https://api.vkeys.cn")
            vip_api_url = self.get_config("music.vip_api_url", "https://www.littleyouzi.com/api/v2")
            juhe_api_url = self.get_config("music.juhe_api_url", "https://api.xcvts.cn/api/music/juhe")
            timeout = self.get_config("music.timeout", 10)
            keyword = search_data.get("keyword", "")
            source = search_data.get("source", "netease")

            # 根据源类型选择合适的适配器
            adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)

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
        """发送音乐信息（调用公共函数）"""
        await send_music_info_to_command(self, music_info, self.get_config)

    @classmethod
    def get_command_info(cls):
        """重写父类方法，返回CommandInfo"""
        from src.plugin_system.base.component_types import CommandInfo, ComponentType

        return CommandInfo(
            name=cls.command_name,
            component_type=ComponentType.COMMAND,
            description=cls.command_description,
            command_pattern=cls.command_pattern,
            enabled=True  # 默认启用，execute()中会检查缓存
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
            search_data = await get_search_cache(search_key)
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
            vip_api_url = self.get_config("music.vip_api_url", "https://www.littleyouzi.com/api/v2")
            juhe_api_url = self.get_config("music.juhe_api_url", "https://api.xcvts.cn/api/music/juhe")
            timeout = self.get_config("music.timeout", 10)
            keyword = search_data.get("keyword", "")
            source = search_data.get("source", "netease")

            # 根据源类型选择合适的适配器
            adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)

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
        """发送音乐信息（调用公共函数）"""
        await send_music_info_to_command(self, music_info, self.get_config)

    @classmethod
    def get_command_info(cls):
        """重写父类方法，返回CommandInfo"""
        from src.plugin_system.base.component_types import CommandInfo, ComponentType

        return CommandInfo(
            name=cls.command_name,
            component_type=ComponentType.COMMAND,
            description=cls.command_description,
            command_pattern=cls.command_pattern,
            enabled=True  # 默认启用，execute()中会检查配置和缓存
        )

# ===== Tool 组件 =====

class PlayMusicTool(BaseTool):
    """播放音乐 Tool - 供AI主动调用"""

    name = "play_music"
    description = "搜索并播放歌曲。重要：调用此工具时必须提供具体歌名。如果用户没指定歌名（如'推首歌'），AI应该根据聊天上下文、用户情绪、喜好等自行推荐一首合适的歌曲，然后将歌名作为参数传给此工具"
    parameters = [
        ("song_name", ToolParamType.STRING, "歌曲名称或歌手+歌名，必填。AI需要填写具体歌名，不能为空", True, None),
        ("source", ToolParamType.STRING, "音乐源，可选netease(网易云)、qq(QQ音乐)、netease_vip(网易云VIP)、qq_vip(QQ音乐VIP)、juhe(聚合点歌)，默认netease", False, ["netease", "qq", "netease_vip", "qq_vip", "juhe"])
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
            vip_api_url = self.get_config("music.vip_api_url", "https://www.littleyouzi.com/api/v2")
            juhe_api_url = self.get_config("music.juhe_api_url", "https://api.xcvts.cn/api/music/juhe")
            timeout = self.get_config("music.timeout", 10)
            default_source = self.get_config("music.default_source", "netease")

            # 确定搜索源
            if user_source:
                all_sources = [user_source]
            else:
                all_sources = ["netease", "qq", "netease_vip", "qq_vip", "juhe"]
                if default_source in all_sources:
                    all_sources.remove(default_source)
                    all_sources.insert(0, default_source)

            # 尝试各个音源搜索
            music_info = None
            successful_source = None

            for source in all_sources:
                for attempt in range(1, 4):  # 每个源尝试3次
                    try:
                        # 根据源类型选择合适的适配器
                        adapter = get_music_adapter(source, api_url, timeout, vip_api_url, juhe_api_url)

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
        """发送音乐到聊天流（调用公共函数）"""
        if not self.chat_stream:
            logger.error("[PlayMusicTool] chat_stream 未初始化")
            return

        stream_id = self.chat_stream.stream_id
        await send_music_info_to_stream(stream_id, music_info, self.get_config)
