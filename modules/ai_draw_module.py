"""
AI绘图模块 - AI Draw功能

调用星知阁AI绘图API根据用户描述词生成图片

功能：
- 智能风格匹配算法
- 图片缓存和换风格
- 支持命令触发
"""

import urllib.parse
import aiohttp
import asyncio
import random
import time
from typing import Tuple, List, Dict, Optional
from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand

logger = get_logger("entertainment_plugin.ai_draw")

# 图片缓存：{chat_id: {"images": [...], "sent_indices": set(), "prompt": str, "timestamp": float}}
_image_cache: Dict[str, Dict] = {}
_image_cache_lock = asyncio.Lock()  # 缓存并发保护
CACHE_EXPIRE_TIME = 300  # 缓存过期时间（秒）- 5分钟
_cache_cleanup_task: Optional[asyncio.Task] = None


async def _cleanup_expired_image_cache():
    """后台任务：定期清理过期的图片缓存"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟检查一次

            async with _image_cache_lock:
                current_time = time.time()
                expired_keys = [
                    key for key, data in _image_cache.items()
                    if current_time - data.get("timestamp", 0) >= CACHE_EXPIRE_TIME
                ]

                for key in expired_keys:
                    del _image_cache[key]

                if expired_keys:
                    logger.info(f"清理了 {len(expired_keys)} 个过期图片缓存")

        except asyncio.CancelledError:
            logger.debug("图片缓存清理任务被取消")
            break
        except Exception as e:
            logger.error(f"图片缓存清理任务出错: {e}", exc_info=True)


def start_image_cache_cleanup():
    """启动图片缓存清理任务"""
    global _cache_cleanup_task
    if _cache_cleanup_task is None or _cache_cleanup_task.done():
        _cache_cleanup_task = asyncio.create_task(_cleanup_expired_image_cache())
        logger.info("图片缓存清理任务已启动")


def calculate_prompt_similarity(user_prompt: str, creation_prompt: str) -> float:
    """
    计算用户描述词和生成提示词的相似度（智能匹配算法）

    算法说明：
    - 使用加权词匹配：风格关键词（如"二次元"、"日系"）权重更高
    - 综合三种匹配方式：子串匹配(60%) + 风格加分(30%) + 字符匹配(10%)
    - 自动降低不符合人设的风格（如"手绘"、"素描"）权重

    Args:
        user_prompt: 用户输入的描述词（如"猫娘 可爱 二次元"）
        creation_prompt: API返回的创作提示词（如"日系二次元插画风格 猫娘少女"）

    Returns:
        相似度分数 (0.0-1.0之间，越高越匹配)
    """
    if not user_prompt or not creation_prompt:
        return 0.0

    # 转换为小写进行匹配
    user_lower = user_prompt.lower()
    creation_lower = creation_prompt.lower()

    # 定义风格关键词及其权重（这些词更重要）
    style_keywords = {
        '二次元': 2.0, '日系': 2.0, '插画': 1.8, '动漫': 1.8,
        'anime': 2.0, '唯美': 1.5, '精致': 1.5, '细腻': 1.5,
        '可爱': 1.3, '萌': 1.3, '猫娘': 1.5, '少女': 1.3,
        # 降低某些不太符合人设的风格权重
        '手绘': 0.5, '绘本': 0.5, '水彩': 0.5, '素描': 0.5
    }

    # 方法1: 加权子串匹配
    substring_score = 0.0
    user_words = user_lower.split()
    total_weight = 0.0

    for word in user_words:
        # 获取该词的权重（默认为1.0）
        weight = style_keywords.get(word, 1.0)
        total_weight += weight

        if word in creation_lower:
            substring_score += weight

    if total_weight > 0:
        substring_score = substring_score / total_weight

    # 方法2: 检查creation_prompt中的风格关键词
    style_bonus = 0.0
    for style_word, weight in style_keywords.items():
        if style_word in creation_lower:
            # 如果用户描述词中也有这个词，给予额外加分
            if style_word in user_lower:
                style_bonus += 0.1 * weight
            # 如果是负权重的词（如"手绘"），扣分
            elif weight < 1.0:
                style_bonus -= 0.1 * (1.0 - weight)

    # 方法3: 字符级匹配 (适合中文单字匹配)
    char_score = 0.0
    user_chars = set(user_lower)
    creation_chars = set(creation_lower)

    if user_chars:
        common_chars = user_chars & creation_chars
        char_score = len(common_chars) / len(user_chars)

    # 综合得分 (子串匹配权重最高，风格加分次之，字符匹配最低)
    final_score = substring_score * 0.6 + style_bonus * 0.3 + char_score * 0.1

    # 确保分数在0-1范围内
    final_score = max(0.0, min(1.0, final_score))

    return final_score


def select_best_image(user_prompt: str, images: List[Dict], mode: str = "best") -> Tuple[List[Dict], int]:
    """
    从多张图片中选择最佳图片（支持三种模式）

    工作原理：
    - best模式：使用智能算法计算每张图的相似度，选择最匹配的
    - random模式：随机选择一张图片
    - all模式：返回所有图片

    Args:
        user_prompt: 用户输入的描述词（如"猫娘 可爱"）
        images: API返回的图片列表，每张图包含url和creation_prompt
        mode: 选择模式
            - "best" = 最佳匹配（默认，优先匹配日系二次元风格）
            - "random" = 随机选择
            - "all" = 返回全部图片

    Returns:
        (选择的图片列表, 选择的索引)
        - 图片列表：包含选中的图片数据
        - 索引：选中图片在原列表中的位置（用于缓存管理）
    """
    if not images:
        return [], -1

    if mode == "all":
        return images, -1
    elif mode == "random":
        idx = random.randint(0, len(images) - 1)
        return [images[idx]], idx
    elif mode == "best":
        # 计算每张图片的匹配分数
        scored_images = []
        for idx, img in enumerate(images):
            creation_prompt = img.get("creation_prompt", "")
            similarity = calculate_prompt_similarity(user_prompt, creation_prompt)
            scored_images.append((similarity, idx, img))
            logger.debug(f"图片相似度: {similarity:.2f} - {creation_prompt[:50]}...")

        # 选择得分最高的图片
        scored_images.sort(key=lambda x: x[0], reverse=True)
        best_score, best_idx, best_image = scored_images[0]

        logger.info(f"选择最佳图片,相似度: {best_score:.2f}")
        return [best_image], best_idx
    else:
        # 默认返回第一张
        return [images[0]], 0


async def get_cached_images(chat_id: str) -> Optional[Dict]:
    """
    获取缓存的图片（线程安全），如果过期则返回None

    Args:
        chat_id: 聊天ID

    Returns:
        缓存数据或None
    """
    async with _image_cache_lock:
        if chat_id not in _image_cache:
            return None

        cache = _image_cache[chat_id]
        # 检查是否过期
        if time.time() - cache.get("timestamp", 0) > CACHE_EXPIRE_TIME:
            del _image_cache[chat_id]
            logger.debug(f"图片缓存已过期并删除: {chat_id}")
            return None

        return cache


async def cache_images(chat_id: str, images: List[Dict], prompt: str, sent_index: int):
    """
    缓存图片列表（线程安全）

    Args:
        chat_id: 聊天ID
        images: 图片列表
        prompt: 描述词
        sent_index: 已发送的图片索引
    """
    async with _image_cache_lock:
        _image_cache[chat_id] = {
            "images": images,
            "sent_indices": {sent_index} if sent_index >= 0 else set(),
            "prompt": prompt,
            "timestamp": time.time()
        }
        logger.debug(f"图片缓存已设置: {chat_id}, 描述词={prompt}, 图片数={len(images)}")


async def get_next_unsent_image(chat_id: str) -> Optional[Tuple[Dict, int]]:
    """
    从缓存中获取下一张未发送的图片（线程安全）

    Args:
        chat_id: 聊天ID

    Returns:
        (图片数据, 索引) 或 None
    """
    async with _image_cache_lock:
        if chat_id not in _image_cache:
            return None

        cache = _image_cache[chat_id]
        # 检查是否过期
        if time.time() - cache.get("timestamp", 0) > CACHE_EXPIRE_TIME:
            del _image_cache[chat_id]
            logger.debug(f"图片缓存已过期: {chat_id}")
            return None

        images = cache["images"]
        sent_indices = cache["sent_indices"]

        # 找到未发送的图片
        for idx, img in enumerate(images):
            if idx not in sent_indices:
                sent_indices.add(idx)
                return img, idx

        # 所有图片都已发送
        return None


class AIDrawCommand(BaseCommand):
    """AI绘图 Command - 手动AI绘图命令"""

    command_name = "ai_draw_command"
    command_description = "根据描述词生成AI图片"

    # 命令匹配模式：/draw <prompt> 或 /绘图 <prompt>
    command_pattern = r"^/(draw|绘图|画图)(?:\s+(?P<prompt>.+))?$"
    command_help = "根据描述词生成AI图片。用法：/draw <描述词> 或 /绘图 <描述词>"
    command_examples = [
        "/draw jk",
        "/draw 可爱的猫咪",
        "/绘图 美丽的风景",
        "/画图 动漫少女"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行AI绘图命令"""
        try:
            # 从配置获取设置
            api_url = self.get_config(
                "ai_draw.api_url",
                "https://api.xingzhige.com/API/DrawOne/"
            )
            default_prompt = self.get_config(
                "ai_draw.default_prompt",
                "jk"
            )
            timeout = self.get_config("ai_draw.timeout", 30)
            selection_mode = self.get_config("ai_draw.selection_mode", "best")

            # 解析命令参数（使用 matched_groups 获取正则匹配结果）
            prompt = self.matched_groups.get("prompt")

            if not prompt or not prompt.strip():
                # 如果没有提供描述词,使用默认值
                prompt = default_prompt
                logger.info(f"未提供描述词,使用默认值: {prompt}")
            else:
                prompt = prompt.strip()
                logger.info(f"用户指定描述词: {prompt}")

            # URL编码描述词
            encoded_prompt = urllib.parse.quote(prompt)
            full_api_url = f"{api_url}?prompt={encoded_prompt}"

            logger.info(f"执行AI绘图命令,描述词: {prompt}, 选择模式: {selection_mode}")

            # 调用API获取图片数据
            async with aiohttp.ClientSession() as session:
                async with session.get(full_api_url, timeout=timeout) as response:
                    if response.status != 200:
                        raise Exception(f"API请求失败,状态码: {response.status}")

                    data = await response.json()

                    if data.get("code") != 200:
                        raise Exception(f"API返回错误: {data.get('msg', '未知错误')}")

                    images = data.get("data", [])
                    if not images:
                        raise Exception("API返回的图片列表为空")

                    logger.info(f"API返回 {len(images)} 张图片")

                    # 根据配置选择图片
                    selected_images, selected_idx = select_best_image(prompt, images, selection_mode)

                    # 缓存所有图片（用于"下一张"功能）
                    chat_id = self.message.chat_stream.stream_id if self.message and self.message.chat_stream else None
                    if chat_id:
                        await cache_images(chat_id, images, prompt, selected_idx)
                        logger.debug(f"已缓存 {len(images)} 张图片，可用于换风格")

                    # 发送图片
                    for idx, img_data in enumerate(selected_images):
                        img_url = img_data.get("url")
                        if img_url:
                            await self.send_custom("imageurl", img_url)
                            creation_prompt = img_data.get("creation_prompt", "")
                            logger.info(
                                f"发送AI绘图 [{idx+1}/{len(selected_images)}] "
                                f"创作提示: {creation_prompt[:50]}..."
                            )

                    return True, f"成功生成并发送 {len(selected_images)} 张AI图片 (描述词: {prompt})", True

        except Exception as e:
            logger.error(f"AI绘图命令执行出错: {e}")
            await self.send_text(f"❌ AI绘图出错: {e}")
            return False, f"AI绘图出错: {e}", True
