"""
AI绘图模块 - AI Draw功能

调用星知阁AI绘图API根据用户描述词生成图片
"""

import urllib.parse
import aiohttp
import random
import time
from typing import Tuple, List, Dict, Optional
from src.common.logger import get_logger
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ChatMode
from src.config.config import global_config

logger = get_logger("entertainment_plugin.ai_draw")

# 图片缓存：{chat_id: {"images": [...], "sent_indices": set(), "prompt": str, "timestamp": float}}
_image_cache: Dict[str, Dict] = {}
# 缓存过期时间（秒）
CACHE_EXPIRE_TIME = 300  # 5分钟


def calculate_prompt_similarity(user_prompt: str, creation_prompt: str) -> float:
    """
    计算用户描述词和生成提示词的相似度

    Args:
        user_prompt: 用户输入的描述词
        creation_prompt: API返回的创作提示词

    Returns:
        相似度分数 (0-1之间)
    """
    if not user_prompt or not creation_prompt:
        return 0.0

    # 转换为小写进行匹配
    user_lower = user_prompt.lower()
    creation_lower = creation_prompt.lower()

    # 方法1: 子串匹配 (适合中文和英文)
    # 检查用户输入的词是否在创作提示中出现
    substring_score = 0.0
    user_words = user_lower.split()

    for word in user_words:
        if word in creation_lower:
            substring_score += 1.0

    if user_words:
        substring_score = substring_score / len(user_words)

    # 方法2: 字符级匹配 (适合中文单字匹配)
    char_score = 0.0
    user_chars = set(user_lower)
    creation_chars = set(creation_lower)

    if user_chars:
        common_chars = user_chars & creation_chars
        char_score = len(common_chars) / len(user_chars)

    # 综合得分 (子串匹配权重更高)
    final_score = substring_score * 0.7 + char_score * 0.3

    return final_score


def select_best_image(user_prompt: str, images: List[Dict], mode: str = "best") -> Tuple[List[Dict], int]:
    """
    从多张图片中选择最佳图片

    Args:
        user_prompt: 用户输入的描述词
        images: API返回的图片列表
        mode: 选择模式 ("best"=最佳匹配, "random"=随机, "all"=全部)

    Returns:
        (选择的图片列表, 选择的索引)
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


def get_cached_images(chat_id: str) -> Optional[Dict]:
    """获取缓存的图片，如果过期则返回None"""
    if chat_id not in _image_cache:
        return None

    cache = _image_cache[chat_id]
    # 检查是否过期
    if time.time() - cache.get("timestamp", 0) > CACHE_EXPIRE_TIME:
        del _image_cache[chat_id]
        return None

    return cache


def cache_images(chat_id: str, images: List[Dict], prompt: str, sent_index: int):
    """缓存图片列表"""
    _image_cache[chat_id] = {
        "images": images,
        "sent_indices": {sent_index} if sent_index >= 0 else set(),
        "prompt": prompt,
        "timestamp": time.time()
    }


def get_next_unsent_image(chat_id: str) -> Optional[Tuple[Dict, int]]:
    """从缓存中获取下一张未发送的图片"""
    cache = get_cached_images(chat_id)
    if not cache:
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


class AIDrawAction(BaseAction):
    """AI绘图 Action 组件 - 智能绘图生成"""

    action_name = "ai_draw_action"
    action_description = "根据描述词生成AI图片"

    # 激活设置
    activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    # 关键词激活
    activation_keywords = ["AI绘图", "ai绘图", "画图", "绘图", "生成图片", "画一张", "画个", "画一个", "画张", "自拍", "来个", "来张", "换个风格", "换一张", "再来一张", "下一张"]
    keyword_case_sensitive = False

    # Action 参数
    action_parameters = {
        "prompt": "图片描述词,用于生成AI图片"
    }
    action_require = [
        "当用户要求AI绘图时使用",
        "当用户说'AI绘图'、'画图'、'画一张'等时使用",
        "当用户说'换个风格'、'换一张'、'再来一张'时使用",
        "当需要根据描述生成图片时使用"
    ]
    associated_types = []  # 移除类型限制，允许在所有适配器中使用

    # 换风格关键词
    CHANGE_STYLE_KEYWORDS = ["换个风格", "换一张", "再来一张", "下一张", "换风格", "另一张", "其他风格"]

    async def execute(self) -> Tuple[bool, str]:
        """执行AI绘图"""
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

            # 从bot_config获取人设信息
            bot_nickname = global_config.bot.nickname  # 小雪
            bot_aliases = global_config.bot.alias_names  # ["雪主子", ...]
            bot_personality = global_config.personality.personality  # 是神秘靓仔养的猫娘...

            # 人设描述词 - 优先使用配置，否则从人设提取关键词
            self_prompt = self.get_config("ai_draw.self_prompt", "")
            if not self_prompt:
                # 从人设自动生成描述词（不含名字，只要特征）
                self_prompt = "二次元少女 可爱 萌"
                # 如果人设包含"猫娘"等关键词，添加到描述词
                if "猫娘" in bot_personality or "猫" in bot_personality:
                    self_prompt = f"猫娘 猫耳 白发 {self_prompt}"
                logger.debug(f"从人设生成描述词: {self_prompt}")

            # 触发人设描述词的关键词 - 从bot_config获取
            self_keywords = ["你自己", "自己", "你", bot_nickname] + list(bot_aliases)

            # 尝试从消息中提取描述词
            message_text = (self.action_message.processed_plain_text or "").strip()

            # 检查是否是换风格请求
            is_change_style = False
            for kw in self.CHANGE_STYLE_KEYWORDS:
                if kw in message_text:
                    is_change_style = True
                    logger.info(f"{self.log_prefix} 检测到换风格关键词'{kw}'")
                    break

            # 如果是换风格，尝试从缓存获取下一张图片
            if is_change_style:
                next_image = get_next_unsent_image(self.chat_id)
                if next_image:
                    img_data, idx = next_image
                    img_url = img_data.get("url")
                    if img_url:
                        await self.send_custom("imageurl", img_url)
                        creation_prompt = img_data.get("creation_prompt", "")
                        cache = get_cached_images(self.chat_id)
                        total = len(cache["images"]) if cache else 0
                        sent_count = len(cache["sent_indices"]) if cache else 0
                        logger.info(
                            f"{self.log_prefix} 换风格：发送缓存图片 [{sent_count}/{total}] "
                            f"创作提示: {creation_prompt[:50]}..."
                        )
                        return True, f"换风格成功，发送第{sent_count}张图片"
                else:
                    # 缓存中没有更多图片，提示用户
                    cache = get_cached_images(self.chat_id)
                    if cache:
                        logger.info(f"{self.log_prefix} 缓存图片已全部发送，重新生成")
                        await self.send_text("之前的图都发完啦，重新画一批~")
                    # 继续执行新的API调用

            # 移除触发关键词,提取描述词
            prompt = default_prompt
            for keyword in self.activation_keywords:
                if keyword in message_text:
                    # 提取关键词后的内容作为描述词
                    parts = message_text.split(keyword, 1)
                    if len(parts) > 1 and parts[1].strip():
                        prompt = parts[1].strip()
                    break

            # 检查是否触发人设描述词 - 在原始消息中检测，而不仅是提取的prompt
            use_self_prompt = False
            for self_kw in self_keywords:
                if self_kw in message_text:  # 改为检测原始消息
                    logger.info(f"{self.log_prefix} 检测到人设关键词'{self_kw}'，使用人设描述词")
                    prompt = self_prompt
                    use_self_prompt = True
                    break

            # 如果是"自拍"类请求且没有明确的其他描述词，也使用人设描述词
            if not use_self_prompt and "自拍" in message_text:
                logger.info(f"{self.log_prefix} 检测到'自拍'请求，使用人设描述词")
                prompt = self_prompt

            logger.info(
                f"{self.log_prefix} 开始AI绘图,描述词: {prompt}, 选择模式: {selection_mode}"
            )

            # URL编码描述词
            encoded_prompt = urllib.parse.quote(prompt)
            full_api_url = f"{api_url}?prompt={encoded_prompt}"

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

                    # 缓存所有图片（用于换风格功能）
                    cache_images(self.chat_id, images, prompt, selected_idx)

                    # 发送图片
                    for idx, img_data in enumerate(selected_images):
                        img_url = img_data.get("url")
                        if img_url:
                            await self.send_custom("imageurl", img_url)
                            creation_prompt = img_data.get("creation_prompt", "")
                            logger.info(
                                f"{self.log_prefix} 发送AI绘图 [{idx+1}/{len(selected_images)}] "
                                f"创作提示: {creation_prompt[:50]}..."
                            )

                    remaining = len(images) - 1 if selection_mode == "best" else 0
                    if remaining > 0:
                        logger.info(f"{self.log_prefix} 还有{remaining}张其他风格可用，说'换个风格'可查看")

                    logger.info(
                        f"{self.log_prefix} AI绘图成功发送 {len(selected_images)} 张图片 (描述词: {prompt})"
                    )
                    return True, f"成功生成并发送 {len(selected_images)} 张AI图片 (描述词: {prompt})"

        except Exception as e:
            logger.error(f"{self.log_prefix} AI绘图出错: {e}")
            await self.send_text(f"❌ AI绘图出错: {e}")
            return False, f"AI绘图出错: {e}"


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
                    selected_images, _ = select_best_image(prompt, images, selection_mode)

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
