"""
AI绘图模块 - AI Draw功能

调用星知阁AI绘图API根据用户描述词生成图片
"""

import urllib.parse
import aiohttp
import random
from typing import Tuple, List, Dict
from src.common.logger import get_logger
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ChatMode

logger = get_logger("entertainment_plugin.ai_draw")


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


def select_best_image(user_prompt: str, images: List[Dict], mode: str = "best") -> List[Dict]:
    """
    从多张图片中选择最佳图片

    Args:
        user_prompt: 用户输入的描述词
        images: API返回的图片列表
        mode: 选择模式 ("best"=最佳匹配, "random"=随机, "all"=全部)

    Returns:
        选择的图片列表
    """
    if not images:
        return []

    if mode == "all":
        return images
    elif mode == "random":
        return [random.choice(images)]
    elif mode == "best":
        # 计算每张图片的匹配分数
        scored_images = []
        for img in images:
            creation_prompt = img.get("creation_prompt", "")
            similarity = calculate_prompt_similarity(user_prompt, creation_prompt)
            scored_images.append((similarity, img))
            logger.debug(f"图片相似度: {similarity:.2f} - {creation_prompt[:50]}...")

        # 选择得分最高的图片
        scored_images.sort(key=lambda x: x[0], reverse=True)
        best_image = scored_images[0][1]
        best_score = scored_images[0][0]

        logger.info(f"选择最佳图片,相似度: {best_score:.2f}")
        return [best_image]
    else:
        # 默认返回第一张
        return [images[0]]


class AIDrawAction(BaseAction):
    """AI绘图 Action 组件 - 智能绘图生成"""

    action_name = "ai_draw_action"
    action_description = "根据描述词生成AI图片"

    # 激活设置
    activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    # 关键词激活
    activation_keywords = ["AI绘图", "ai绘图", "画图", "绘图", "生成图片", "画一张"]
    keyword_case_sensitive = False

    # Action 参数
    action_parameters = {
        "prompt": "图片描述词,用于生成AI图片"
    }
    action_require = [
        "当用户要求AI绘图时使用",
        "当用户说'AI绘图'、'画图'、'画一张'等时使用",
        "当需要根据描述生成图片时使用"
    ]
    associated_types = ["image", "ai", "draw"]

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

            # 尝试从消息中提取描述词
            # 用户消息格式可能是: "AI绘图 描述词" 或 "画一张 描述词"
            message_text = self.event.get_plain_text().strip()

            # 移除触发关键词,提取描述词
            prompt = default_prompt
            for keyword in self.activation_keywords:
                if keyword in message_text:
                    # 提取关键词后的内容作为描述词
                    parts = message_text.split(keyword, 1)
                    if len(parts) > 1 and parts[1].strip():
                        prompt = parts[1].strip()
                    break

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
                    selected_images = select_best_image(prompt, images, selection_mode)

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
                    selected_images = select_best_image(prompt, images, selection_mode)

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
