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
import base64
import asyncio
import time
import os
try:
    import io
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
from src.plugin_system.apis import send_api, chat_api, database_api
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ChatMode
)
from src.plugin_system.base.config_types import ConfigField
from src.common.logger import get_logger

logger = get_logger("music_plugin")


# ===== 全局搜索缓存 =====
# 用于存储用户的搜索结果（键: search_key, 值: {keyword, results, timestamp, source}）
_search_cache = {}
_CACHE_TTL = 1800  # 30分钟


def get_search_cache(key: str) -> Optional[dict]:
    """获取搜索缓存"""
    if key in _search_cache:
        cache_data = _search_cache[key]
        # 检查是否过期
        if time.time() - cache_data.get("timestamp", 0) < _CACHE_TTL:
            return cache_data
        else:
            # 删除过期缓存
            del _search_cache[key]
    return None


def set_search_cache(key: str, keyword: str, results: List[dict], source: str = "netease"):
    """设置搜索缓存"""
    _search_cache[key] = {
        "keyword": keyword,
        "results": results,
        "source": source,  # 记录音乐源
        "timestamp": time.time()
    }


# ===== 音乐源适配器 =====

class MusicSourceAdapter:
    """音乐源适配器基类"""

    def __init__(self, api_url: str, timeout: int):
        self.api_url = api_url
        self.timeout = timeout
        self.source_name = "unknown"
        self.source_display_name = "未知"

    async def search_list(self, keyword: str, page: int = 1, num: int = 10) -> Optional[List[dict]]:
        """搜索音乐列表"""
        raise NotImplementedError

    async def get_music_detail(self, keyword: str, choose: int, quality: str) -> Optional[dict]:
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
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                params = {"word": keyword, "page": page, "num": num}
                async with session.get(f"{self.api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            result_data = data.get("data", [])
                            if isinstance(result_data, list) and len(result_data) > 0:
                                return [self.normalize_music_info(item) for item in result_data]
                            elif isinstance(result_data, dict):
                                return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[NeteaseAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int, quality: str) -> Optional[dict]:
        """获取网易云音乐详情"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                params = {"word": keyword, "choose": choose, "quality": quality}
                async with session.get(f"{self.api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
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
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                params = {"word": keyword, "page": page, "num": num}
                async with session.get(f"{self.api_url}/v2/music/tencent", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
                            result_data = data.get("data", [])
                            if isinstance(result_data, list) and len(result_data) > 0:
                                return [self.normalize_music_info(item) for item in result_data]
                            elif isinstance(result_data, dict):
                                return [self.normalize_music_info(result_data)]
        except Exception as e:
            logger.error(f"[QQMusicAdapter] 搜索失败: {e}")
        return None

    async def get_music_detail(self, keyword: str, choose: int, quality: str) -> Optional[dict]:
        """获取QQ音乐详情"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                params = {"word": keyword, "choose": choose, "quality": quality}
                async with session.get(f"{self.api_url}/v2/music/tencent", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200:
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


# ===== 公共工具方法 =====

async def call_music_api(
    api_url: str,
    song_name: str,
    timeout: int,
    retries: int = 3,
    base_delay: float = 1.0,
    quality: str = "9",
    choose: int = 1,
    log_prefix: str = "[MusicAPI]"
) -> Optional[dict]:
    """
    调用音乐API搜索歌曲，带指数退避重试机制

    Args:
        api_url: API基础URL
        song_name: 歌曲名称
        timeout: 请求超时时间
        retries: 重试次数
        base_delay: 基础延迟时间（指数退避的基数）
        quality: 音质等级（1=标准64k, 5=SQ无损, 9=母带音质）
        choose: 选择第几首歌（1-based）
        log_prefix: 日志前缀

    Returns:
        音乐信息字典，失败返回None
    """
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                params = {
                    "word": song_name,
                    "choose": choose,
                    "quality": quality
                }

                logger.debug(f"{log_prefix} 请求参数: {params}")

                async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"{log_prefix} API 响应: code={data.get('code')}, message={data.get('message', 'N/A')}")

                        if data.get("code") == 200:
                            result_data = data.get("data", {})

                            # 如果返回的是列表，取第一个结果
                            if isinstance(result_data, list) and len(result_data) > 0:
                                result_data = result_data[0]
                                logger.info(f"{log_prefix} API返回列表，选择第一个结果")

                            if result_data and isinstance(result_data, dict):
                                logger.info(f"{log_prefix} 成功获取音乐信息: {song_name[:30]}")
                                logger.debug(f"{log_prefix} 返回数据字段: {list(result_data.keys())}")
                                return result_data
                            else:
                                logger.warning(f"{log_prefix} API返回成功但数据为空或格式错误 (尝试 {attempt}/{retries}), data类型: {type(result_data)}")
                        else:
                            error_msg = data.get('message', '未知错误')
                            logger.warning(f"{log_prefix} API返回错误 (尝试 {attempt}/{retries}): {error_msg}")
                    else:
                        logger.warning(f"{log_prefix} API请求失败 (尝试 {attempt}/{retries}), 状态码: {response.status}")

        except asyncio.TimeoutError:
            logger.error(f"{log_prefix} 请求超时 (尝试 {attempt}/{retries})")
        except Exception as e:
            logger.error(f"{log_prefix} 请求异常 (尝试 {attempt}/{retries}): {type(e).__name__}: {e}")

        # 指数退避重试
        if attempt < retries:
            delay = base_delay * (2 ** (attempt - 1))
            logger.info(f"{log_prefix} 等待 {delay:.1f}秒后重试...")
            await asyncio.sleep(delay)

    logger.error(f"{log_prefix} 所有重试均失败，歌曲: {song_name[:30]}")
    return None


async def search_music_list(
    api_url: str,
    song_name: str,
    timeout: int,
    page: int = 1,
    num: int = 10,
    log_prefix: str = "[MusicSearch]"
) -> Optional[List[dict]]:
    """
    搜索音乐列表（不指定choose参数）

    Args:
        api_url: API基础URL
        song_name: 歌曲名称
        timeout: 请求超时时间
        page: 页码
        num: 每页结果数
        log_prefix: 日志前缀

    Returns:
        音乐列表，失败返回None
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            params = {
                "word": song_name,
                "page": page,
                "num": num
            }

            logger.debug(f"{log_prefix} 搜索参数: {params}")

            async with session.get(f"{api_url}/v2/music/netease", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"{log_prefix} API 响应: code={data.get('code')}, message={data.get('message', 'N/A')}")

                    if data.get("code") == 200:
                        result_data = data.get("data", [])

                        if isinstance(result_data, list) and len(result_data) > 0:
                            logger.info(f"{log_prefix} 搜索到 {len(result_data)} 首歌曲")
                            return result_data
                        elif isinstance(result_data, dict):
                            # 如果返回的是单个对象，转换为列表
                            logger.info(f"{log_prefix} API返回单个结果，转换为列表")
                            return [result_data]
                        else:
                            logger.warning(f"{log_prefix} 未找到搜索结果")
                            return []
                    else:
                        error_msg = data.get('message', '未知错误')
                        logger.warning(f"{log_prefix} API返回错误: {error_msg}")
                else:
                    logger.warning(f"{log_prefix} API请求失败，状态码: {response.status}")

    except asyncio.TimeoutError:
        logger.error(f"{log_prefix} 请求超时")
    except Exception as e:
        logger.error(f"{log_prefix} 请求异常: {type(e).__name__}: {e}")

    return None


async def download_image_base64(
    url: str,
    timeout: int = 10,
    max_size: int = 5 * 1024 * 1024,  # 5MB
    log_prefix: str = "[ImageDownload]"
) -> Optional[str]:
    """
    异步下载图片并转为base64

    Args:
        url: 图片URL
        timeout: 超时时间
        max_size: 最大文件大小（字节）
        log_prefix: 日志前缀

    Returns:
        base64编码的图片，失败返回None
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"{log_prefix} 下载失败，状态码: {response.status}")
                    return None

                # 检查内容类型
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith('image/'):
                    logger.warning(f"{log_prefix} 非图片类型: {content_type}")
                    return None

                # 检查文件大小
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > max_size:
                    logger.warning(f"{log_prefix} 文件过大: {int(content_length)} > {max_size}")
                    return None

                # 读取内容
                content = await response.read()
                if len(content) > max_size:
                    logger.warning(f"{log_prefix} 实际内容过大: {len(content)} > {max_size}")
                    return None

                return base64.b64encode(content).decode('utf-8')

    except asyncio.TimeoutError:
        logger.warning(f"{log_prefix} 下载超时: {url[:50]}")
    except Exception as e:
        logger.warning(f"{log_prefix} 下载失败: {type(e).__name__}: {e}")

    return None


def generate_music_list_image(music_list: List[dict], search_keyword: str, source_name: str = "") -> Optional[str]:
    """
    生成歌曲列表图片（如果PIL不可用或无中文字体则返回None）

    Args:
        music_list: 歌曲列表
        search_keyword: 搜索关键词

    Returns:
        base64编码的图片，失败或PIL不可用返回None
    """
    if not PIL_AVAILABLE:
        logger.warning("[ImageGen] PIL未安装，无法生成列表图片")
        return None

    try:
        # 尝试查找支持中文的字体
        chinese_font_paths = [
            # Noto CJK fonts
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            # WenQuanYi fonts
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            # Droid fonts
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            # System fonts (common on some systems)
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
        ]

        font_path = None
        for path in chinese_font_paths:
            try:
                if os.path.exists(path):
                    font_path = path
                    logger.info(f"[ImageGen] 找到中文字体: {path}")
                    break
            except:
                continue

        if not font_path:
            logger.warning("[ImageGen] 未找到支持中文的字体，无法生成图片列表")
            logger.info("[ImageGen] 提示：可以安装中文字体 'sudo apt-get install fonts-noto-cjk'")
            return None

        # 图片设置
        width = 800
        item_height = 80
        header_height = 100
        footer_height = 40
        padding = 20
        height = header_height + len(music_list) * item_height + footer_height

        # 创建图片
        img = Image.new('RGB', (width, height), color='#F5F5F5')
        draw = ImageDraw.Draw(img)

        try:
            # 加载中文字体
            title_font = ImageFont.truetype(font_path, 28)
            text_font = ImageFont.truetype(font_path, 18)
            small_font = ImageFont.truetype(font_path, 14)
        except Exception as e:
            logger.error(f"[ImageGen] 加载字体失败: {e}")
            return None

        # 绘制头部
        draw.rectangle([0, 0, width, header_height], fill='#1DB954')
        title_text = f"搜索结果: {search_keyword}"
        if source_name:
            title_text += f" [{source_name}]"
        draw.text((padding, 30), title_text, font=title_font, fill='white')
        draw.text((padding, 70), f"找到 {len(music_list)} 首歌曲，输入 /choose 序号 来选择", font=small_font, fill='white')

        # 绘制歌曲列表
        y = header_height
        for idx, music in enumerate(music_list, 1):
            # 背景色交替
            bg_color = '#FFFFFF' if idx % 2 == 1 else '#F0F0F0'
            draw.rectangle([0, y, width, y + item_height], fill=bg_color)

            # 序号
            draw.text((padding, y + 10), f"#{idx}", font=text_font, fill='#1DB954')

            # 歌曲信息
            song = music.get('song', '未知')[:25]
            singer = music.get('singer', '未知')[:20]
            album = music.get('album', '未知')[:20]

            draw.text((padding + 50, y + 10), song, font=text_font, fill='#333333')
            draw.text((padding + 50, y + 40), f"{singer} - {album}", font=small_font, fill='#666666')

            y += item_height

        # 绘制底部
        draw.rectangle([0, height - footer_height, width, height], fill='#333333')
        draw.text((padding, height - 30), "提示: 使用 /choose <序号> 选择歌曲", font=small_font, fill='white')

        # 转换为base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        logger.info(f"[ImageGen] 成功生成歌曲列表图片，共 {len(music_list)} 首歌")
        return img_base64

    except Exception as e:
        logger.error(f"[ImageGen] 生成歌曲列表图片失败: {e}", exc_info=True)
        return None


def generate_music_list_text(music_list: List[dict], search_keyword: str, source_name: str = "") -> str:
    """
    生成歌曲列表文本

    Args:
        music_list: 歌曲列表
        search_keyword: 搜索关键词
        source_name: 音乐源名称

    Returns:
        格式化的文本列表
    """
    text = f"🎵 搜索结果：{search_keyword}"
    if source_name:
        text += f" [{source_name}]"
    text += f"\n找到 {len(music_list)} 首歌曲\n"
    text += "=" * 40 + "\n\n"

    for idx, music in enumerate(music_list, 1):
        song = music.get('song', '未知')
        singer = music.get('singer', '未知')
        album = music.get('album', '未知')

        text += f"#{idx}  {song}\n"
        text += f"     歌手: {singer}\n"
        text += f"     专辑: {album}\n\n"

    text += "=" * 40 + "\n"
    text += "💡 输入 /choose <序号> 来选择歌曲"

    return text

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

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行音乐点歌命令 - 返回搜索列表"""
        try:
            # 获取匹配的参数
            song_name = (self.matched_groups or {}).get("song_name", "").strip()

            if not song_name:
                await self.send_text("❌ 请输入正确的格式：/music 歌曲名")
                return False, "缺少歌曲名称", True

            # 从配置获取设置
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            max_results = self.get_config("music.max_search_results", 10)

            # 获取配置的音乐源
            current_source = self.get_config("music.default_source", "netease")

            logger.info(f"{self.get_log_prefix()} 搜索音乐列表，关键词：{song_name[:50]}... 音乐源：{current_source}")

            # 使用适配器搜索音乐列表
            adapter = get_music_adapter(current_source, api_url, timeout)
            music_list = await adapter.search_list(song_name, page=1, num=max_results)

            if not music_list or len(music_list) == 0:
                await self.send_text("❌ 未找到相关音乐，请尝试其他关键词")
                return False, "未找到音乐", True

            source_display_name = adapter.source_display_name

            # 存储搜索结果到缓存
            # 从消息上下文获取用户信息
            user_id = self.message_context.user_id if hasattr(self, 'message_context') else "unknown"
            group_id = self.message_context.group_id if hasattr(self, 'message_context') and hasattr(self.message_context, 'group_id') else None

            search_key = f"music_search_{user_id}"
            if group_id:
                search_key = f"music_search_{group_id}_{user_id}"

            # 存储搜索结果（有效期30分钟）- 保存音乐源信息
            set_search_cache(search_key, song_name, music_list, source=current_source)

            logger.info(f"{self.get_log_prefix()} 已保存 {len(music_list)} 个搜索结果到缓存: {search_key}")

            # 尝试生成图片列表 - 传入音乐源名称
            img_base64 = generate_music_list_image(music_list, song_name, source_display_name)

            if img_base64:
                # 发送图片列表
                await self.send_custom(message_type="image", content=img_base64)
                logger.info(f"{self.get_log_prefix()} 发送歌曲列表图片成功")
            else:
                # 发送文本列表 - 传入音乐源名称
                list_text = generate_music_list_text(music_list, song_name, source_display_name)
                await self.send_text(list_text)
                logger.info(f"{self.get_log_prefix()} 发送歌曲列表文本成功")

            return True, f"搜索到 {len(music_list)} 首歌曲", True

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 搜索命令执行出错: {e}", exc_info=True)
            await self.send_text(f"❌ 搜索失败: {str(e)}")
            return False, f"搜索失败: {e}", True

    async def _send_detailed_music_info(self, music_info: dict):
        """发送详细音乐信息"""
        try:
            # 记录收到的数据字段
            logger.info(f"{self.get_log_prefix()} 收到音乐数据字段: {list(music_info.keys())}")

            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            size = music_info.get("size", "未知大小")
            quality = music_info.get("quality", "未知音质")
            cover = music_info.get("cover", "")
            link = music_info.get("link", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")

            logger.info(f"{self.get_log_prefix()} URL字段值: '{url}', 长度: {len(url) if url else 0}")

            # 构建详细消息内容
            message = f"🎵 【点歌成功】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"
            message += f"📦 大小：{size}\n"
            message += f"📊 音质：{quality}\n"

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

            # 发送封面图片（异步下载）
            if cover and self.get_config("features.show_cover", True):
                timeout = self.get_config("api.timeout", 10)
                max_image_size = self.get_config("features.max_image_size", 5 * 1024 * 1024)

                base64_image = await download_image_base64(
                    cover,
                    timeout=timeout,
                    max_size=max_image_size,
                    log_prefix=self.get_log_prefix()
                )

                if base64_image:
                    await self.send_custom(message_type="image", content=base64_image)
                    logger.info(f"{self.get_log_prefix()} 发送封面成功")
                else:
                    logger.warning(f"{self.get_log_prefix()} 封面下载失败")

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送详细音乐信息出错: {e}", exc_info=True)
            await self.send_text("❌ 发送音乐信息时出现错误")


# ===== Choose Command =====

class ChooseCommand(BaseCommand):
    """选择歌曲Command - 从搜索列表中选择"""

    command_name = "choose"
    command_description = "从搜索结果中选择歌曲"
    command_pattern = r"^/choose\s+(?P<index>\d+)$"
    command_help = "选择歌曲命令，用法：/choose 序号"
    command_examples = ["/choose 1", "/choose 3"]
    intercept_message = True

    def get_log_prefix(self) -> str:
        """获取日志前缀"""
        return f"[ChooseCommand]"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行选择歌曲命令"""
        try:
            # 获取序号
            index_str = (self.matched_groups or {}).get("index", "").strip()

            if not index_str:
                await self.send_text("❌ 请输入正确的格式：/choose 序号")
                return False, "缺少序号", True

            index = int(index_str)

            # 获取存储的搜索结果
            # 从消息上下文获取用户信息
            user_id = self.message_context.user_id if hasattr(self, 'message_context') else "unknown"
            group_id = self.message_context.group_id if hasattr(self, 'message_context') and hasattr(self.message_context, 'group_id') else None

            search_key = f"music_search_{user_id}"
            if group_id:
                search_key = f"music_search_{group_id}_{user_id}"

            search_data = get_search_cache(search_key)

            if not search_data:
                await self.send_text("❌ 没有找到搜索记录，请先使用 /music 搜索歌曲")
                return False, "无搜索记录", True

            music_list = search_data.get("results", [])

            if index < 1 or index > len(music_list):
                await self.send_text(f"❌ 序号超出范围，请输入 1-{len(music_list)} 之间的数字")
                return False, "序号超出范围", True

            # 获取选中的歌曲
            selected_music = music_list[index - 1]
            song_name = selected_music.get("song", "未知")

            logger.info(f"{self.get_log_prefix()} 用户选择第 {index} 首歌曲：{song_name}")

            # 使用 choose 参数重新获取完整的歌曲信息（包含 URL）
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            keyword = search_data.get("keyword", "")

            # 获取缓存中的音乐源
            source = search_data.get("source", "netease")

            # 根据音乐源获取对应的音质配置
            if source == "qq":
                quality = self.get_config("music.qq_quality", "14")
            else:
                quality = self.get_config("music.netease_quality", "7")

            logger.info(f"{self.get_log_prefix()} 使用音乐源: {source}, 音质: {quality}")

            # 使用适配器获取完整歌曲信息
            adapter = get_music_adapter(source, api_url, timeout)
            music_info = await adapter.get_music_detail(keyword, index, quality)

            if music_info:
                # 发送音乐信息
                await self._send_music_info(music_info)
                logger.info(f"{self.get_log_prefix()} 成功播放歌曲：{song_name}")
                return True, f"成功播放：{song_name[:30]}...", True
            else:
                await self.send_text("❌ 获取歌曲详情失败，请重新搜索")
                return False, "获取歌曲详情失败", True

        except ValueError:
            await self.send_text("❌ 请输入有效的数字")
            return False, "序号格式错误", True
        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 选择命令执行出错: {e}", exc_info=True)
            await self.send_text(f"❌ 选择失败: {str(e)}")
            return False, f"选择失败: {e}", True

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息"""
        try:
            logger.info(f"{self.get_log_prefix()} 收到音乐数据字段: {list(music_info.keys())}")

            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            size = music_info.get("size", "未知大小")
            quality = music_info.get("quality", "未知音质")
            cover = music_info.get("cover", "")
            link = music_info.get("link", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")

            # 构建详细消息内容
            message = f"🎵 【正在播放】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"
            message += f"📦 大小：{size}\n"
            message += f"📊 音质：{quality}\n"

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
                    logger.info(f"{self.get_log_prefix()} 发送语音消息成功")
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

            # 发送封面图片（异步下载）
            if cover and self.get_config("features.show_cover", True):
                timeout = self.get_config("api.timeout", 10)
                max_image_size = self.get_config("features.max_image_size", 5 * 1024 * 1024)

                base64_image = await download_image_base64(
                    cover,
                    timeout=timeout,
                    max_size=max_image_size,
                    log_prefix=self.get_log_prefix()
                )

                if base64_image:
                    await self.send_custom(message_type="image", content=base64_image)
                    logger.info(f"{self.get_log_prefix()} 发送封面成功")
                else:
                    logger.warning(f"{self.get_log_prefix()} 封面下载失败")

            # 🎵 相似推荐功能
            if self.get_config("features.enable_recommendation", True):
                await self._send_recommendation(singer, song)

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送音乐信息出错: {e}", exc_info=True)
            await self.send_text("❌ 发送音乐信息时出现错误")

    async def _send_recommendation(self, singer: str, current_song: str):
        """发送相似推荐"""
        try:
            logger.info(f"{self.get_log_prefix()} 开始生成相似推荐，歌手：{singer}")

            # 获取配置
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            current_source = self.get_config("music.default_source", "netease")
            max_recommendations = self.get_config("features.max_recommendations", 5)

            # 搜索该歌手的其他歌曲
            adapter = get_music_adapter(current_source, api_url, timeout)
            music_list = await adapter.search_list(singer, page=1, num=max_recommendations + 5)

            if not music_list or len(music_list) == 0:
                logger.info(f"{self.get_log_prefix()} 未找到推荐歌曲")
                return

            # 过滤掉当前播放的歌曲
            recommendations = [m for m in music_list if m.get("song") != current_song][:max_recommendations]

            if len(recommendations) == 0:
                logger.info(f"{self.get_log_prefix()} 过滤后无推荐歌曲")
                return

            # 构建推荐消息
            message = f"\n💡 相似推荐（{singer}的其他歌曲）：\n"
            for idx, music in enumerate(recommendations, 1):
                song = music.get("song", "未知")[:20]
                album = music.get("album", "未知")[:15]
                message += f"{idx}. {song} - {album}\n"

            message += f"\n输入 /music {singer} 查看更多"

            await self.send_text(message)
            logger.info(f"{self.get_log_prefix()} 发送推荐成功，共 {len(recommendations)} 首")

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送推荐出错: {e}", exc_info=True)
            # 推荐失败不影响主流程，只记录日志


# ===== 数字快捷选择Command =====

class QuickChooseCommand(BaseCommand):
    """数字快捷选择Command - 直接输入数字选歌"""

    command_name = "quick_choose"
    command_description = "快捷选择歌曲（直接输入数字）"
    command_pattern = r"^(?P<index>\d+)$"  # 匹配纯数字，使用命名组
    command_help = "快捷选择歌曲，用法：直接输入数字 1-10"
    command_examples = ["1", "5", "10"]
    intercept_message = True

    def get_log_prefix(self) -> str:
        """获取日志前缀"""
        return f"[QuickChooseCommand]"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行快捷选择 - 重用ChooseCommand的逻辑"""
        try:
            # 检查是否启用快捷选择
            if not self.get_config("features.enable_quick_choose", True):
                return False, "快捷选择未启用", False  # 不拦截消息

            # 获取数字
            index_str = (self.matched_groups or {}).get("index", "").strip()
            if not index_str:
                return False, "匹配失败", False

            index = int(index_str)

            # 只接受1-10的数字（避免误触发）
            if index < 1 or index > 10:
                return False, "数字超出范围", False  # 不拦截消息

            # 获取搜索缓存
            user_id = self.message_context.user_id if hasattr(self, 'message_context') else "unknown"
            group_id = self.message_context.group_id if hasattr(self, 'message_context') and hasattr(self.message_context, 'group_id') else None

            search_key = f"music_search_{user_id}"
            if group_id:
                search_key = f"music_search_{group_id}_{user_id}"

            search_data = get_search_cache(search_key)

            # 如果没有缓存，不处理（让消息正常流转）
            if not search_data:
                return False, "无搜索缓存", False  # 不拦截消息

            music_list = search_data.get("results", [])

            # 验证范围
            if index > len(music_list):
                await self.send_text(f"❌ 序号超出范围，当前列表只有 {len(music_list)} 首歌曲")
                return False, "序号超出范围", True  # 拦截消息

            # 获取选中的歌曲
            selected_music = music_list[index - 1]
            song_name = selected_music.get("song", "未知")

            logger.info(f"{self.get_log_prefix()} 用户快捷选择第 {index} 首歌曲：{song_name}")

            # 使用适配器获取完整歌曲信息
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            keyword = search_data.get("keyword", "")
            source = search_data.get("source", "netease")

            # 根据音乐源获取对应的音质配置
            if source == "qq":
                quality = self.get_config("music.qq_quality", "14")
            else:
                quality = self.get_config("music.netease_quality", "7")

            logger.info(f"{self.get_log_prefix()} 使用音乐源: {source}, 音质: {quality}")

            adapter = get_music_adapter(source, api_url, timeout)
            music_info = await adapter.get_music_detail(keyword, index, quality)

            if music_info:
                # 发送音乐信息
                await self._send_music_info(music_info)
                logger.info(f"{self.get_log_prefix()} 快捷播放成功：{song_name}")
                return True, f"快捷播放：{song_name[:30]}...", True
            else:
                await self.send_text("❌ 获取歌曲详情失败，请重新搜索")
                return False, "获取歌曲详情失败", True

        except ValueError:
            return False, "数字格式错误", False
        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 快捷选择出错: {e}", exc_info=True)
            await self.send_text(f"❌ 快捷选择失败: {str(e)}")
            return False, f"快捷选择失败: {e}", True

    async def _send_music_info(self, music_info: dict):
        """发送音乐信息（复用ChooseCommand的逻辑）"""
        try:
            logger.info(f"{self.get_log_prefix()} 收到音乐数据字段: {list(music_info.keys())}")

            song = music_info.get("song", "未知歌曲")
            singer = music_info.get("singer", "未知歌手")
            album = music_info.get("album", "未知专辑")
            interval = music_info.get("interval", "未知时长")
            size = music_info.get("size", "未知大小")
            quality = music_info.get("quality", "未知音质")
            cover = music_info.get("cover", "")
            link = music_info.get("link", "")
            url = music_info.get("url", "")
            song_id = music_info.get("id", "")

            # 构建详细消息内容
            message = f"🎵 【正在播放】\n\n"
            message += f"🎤 歌曲：{song}\n"
            message += f"🎙️ 歌手：{singer}\n"
            message += f"💿 专辑：{album}\n"
            message += f"⏱️ 时长：{interval}\n"
            message += f"📦 大小：{size}\n"
            message += f"📊 音质：{quality}\n"

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
                    logger.info(f"{self.get_log_prefix()} 发送语音消息成功")
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

            # 发送封面图片（异步下载）
            if cover and self.get_config("features.show_cover", True):
                timeout = self.get_config("api.timeout", 10)
                max_image_size = self.get_config("features.max_image_size", 5 * 1024 * 1024)

                base64_image = await download_image_base64(
                    cover,
                    timeout=timeout,
                    max_size=max_image_size,
                    log_prefix=self.get_log_prefix()
                )

                if base64_image:
                    await self.send_custom(message_type="image", content=base64_image)
                    logger.info(f"{self.get_log_prefix()} 发送封面成功")
                else:
                    logger.warning(f"{self.get_log_prefix()} 封面下载失败")

            # 🎵 相似推荐功能
            if self.get_config("features.enable_recommendation", True):
                await self._send_recommendation(singer, song)

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送音乐信息出错: {e}", exc_info=True)
            await self.send_text("❌ 发送音乐信息时出现错误")

    async def _send_recommendation(self, singer: str, current_song: str):
        """发送相似推荐"""
        try:
            logger.info(f"{self.get_log_prefix()} 开始生成相似推荐，歌手：{singer}")

            # 获取配置
            api_url = self.get_config("api.base_url", "https://api.vkeys.cn")
            timeout = self.get_config("api.timeout", 10)
            current_source = self.get_config("music.default_source", "netease")
            max_recommendations = self.get_config("features.max_recommendations", 5)

            # 搜索该歌手的其他歌曲
            adapter = get_music_adapter(current_source, api_url, timeout)
            music_list = await adapter.search_list(singer, page=1, num=max_recommendations + 5)

            if not music_list or len(music_list) == 0:
                logger.info(f"{self.get_log_prefix()} 未找到推荐歌曲")
                return

            # 过滤掉当前播放的歌曲
            recommendations = [m for m in music_list if m.get("song") != current_song][:max_recommendations]

            if len(recommendations) == 0:
                logger.info(f"{self.get_log_prefix()} 过滤后无推荐歌曲")
                return

            # 构建推荐消息
            message = f"\n💡 相似推荐（{singer}的其他歌曲）：\n"
            for idx, music in enumerate(recommendations, 1):
                song = music.get("song", "未知")[:20]
                album = music.get("album", "未知")[:15]
                message += f"{idx}. {song} - {album}\n"

            message += f"\n输入 /music {singer} 查看更多"

            await self.send_text(message)
            logger.info(f"{self.get_log_prefix()} 发送推荐成功，共 {len(recommendations)} 首")

        except Exception as e:
            logger.error(f"{self.get_log_prefix()} 发送推荐出错: {e}", exc_info=True)
            # 推荐失败不影响主流程，只记录日志


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
    python_dependencies = ["aiohttp", "Pillow"]  # Python包依赖列表（Pillow用于生成列表图片，可选）

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
            "timeout": ConfigField(type=int, default=10, description="API请求超时时间(秒)"),
            "retries": ConfigField(type=int, default=3, description="API请求失败重试次数"),
            "base_delay": ConfigField(type=float, default=1.0, description="重试基础延迟时间（秒，使用指数退避）")
        },
        "music": {
            "default_source": ConfigField(
                type=str,
                default="netease",
                description="默认音乐源(netease=网易云音乐, qq=QQ音乐)"
            ),
            "netease_quality": ConfigField(
                type=str,
                default="7",
                description="网易云音乐默认音质等级(1-9)"
            ),
            "qq_quality": ConfigField(
                type=str,
                default="14",
                description="QQ音乐默认音质等级(0-16, 推荐14)"
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
            "send_as_voice": ConfigField(type=bool, default=False, description="是否以语音消息发送音乐（true=语音消息，false=音乐卡片）"),
            "max_image_size": ConfigField(type=int, default=5242880, description="最大封面图片大小（字节，默认5MB）"),
            "enable_quick_choose": ConfigField(type=bool, default=True, description="是否启用数字快捷选择（直接输入1-10选歌）"),
            "enable_recommendation": ConfigField(type=bool, default=True, description="是否启用相似推荐功能"),
            "max_recommendations": ConfigField(type=int, default=5, description="最大推荐歌曲数量")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        components = []

        # 只启用Command组件
        if self.get_config("components.command_enabled", True):
            components.append((MusicCommand.get_command_info(), MusicCommand))
            components.append((ChooseCommand.get_command_info(), ChooseCommand))
            components.append((QuickChooseCommand.get_command_info(), QuickChooseCommand))

        return components
