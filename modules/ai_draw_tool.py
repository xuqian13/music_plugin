"""
AI绘图工具模块 - 供LLM调用的Tool版本

通过LLM的tool_call来智能调用AI绘图功能
"""

import urllib.parse
import aiohttp
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool
from src.plugin_system.base.component_types import ToolParamType
from src.plugin_system.apis import send_api
from src.config.config import global_config

logger = get_logger("entertainment_plugin.ai_draw_tool")

# 图片缓存：{chat_id: {"images": [...], "sent_indices": set(), "prompt": str, "timestamp": float}}
_image_cache: Dict[str, Dict] = {}
CACHE_EXPIRE_TIME = 300  # 5分钟


def get_cached_images(chat_id: str) -> Optional[Dict]:
    """获取缓存的图片"""
    if chat_id not in _image_cache:
        return None
    cache = _image_cache[chat_id]
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
    for idx, img in enumerate(images):
        if idx not in sent_indices:
            sent_indices.add(idx)
            return img, idx
    return None


def select_best_image(user_prompt: str, images: List[Dict]) -> Tuple[Dict, int]:
    """选择最佳匹配的图片"""
    if not images:
        return {}, -1

    best_score = -1
    best_idx = 0
    best_img = images[0]

    user_lower = user_prompt.lower()
    user_chars = set(user_lower)

    for idx, img in enumerate(images):
        creation_prompt = img.get("creation_prompt", "").lower()
        creation_chars = set(creation_prompt)

        # 计算字符重叠度
        if user_chars:
            score = len(user_chars & creation_chars) / len(user_chars)
        else:
            score = 0

        if score > best_score:
            best_score = score
            best_idx = idx
            best_img = img

    return best_img, best_idx


class AIDrawTool(BaseTool):
    """AI绘图工具 - 供LLM调用"""

    name = "ai_draw"
    description = """根据描述生成AI图片。使用场景：
- 用户要求画图、绘图、生成图片时
- 用户说"画一张xxx"、"画个xxx"、"来张xxx"时
- 用户要求画"你自己"、"自拍"、"小雪"等（会自动使用人设描述词）
- 用户说"换个风格"、"再来一张"时（会发送之前缓存的其他风格图片）"""

    parameters = [
        ("prompt", ToolParamType.STRING, "图片描述词，如'猫娘'、'风景'、'jk少女'等。如果用户要求画'你自己'或bot的名字，请填写'self'", True, None),
        ("change_style", ToolParamType.BOOLEAN, "是否切换风格（发送缓存的其他图片），用户说'换个风格'、'再来一张'时设为true", False, None),
    ]

    available_for_llm = True

    async def execute(self, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """执行AI绘图"""
        prompt = function_args.get("prompt", "")
        change_style = function_args.get("change_style", False)

        chat_id = self.chat_id
        if not chat_id:
            return {"success": False, "message": "无法获取聊天ID"}

        try:
            # 获取配置
            api_url = self.get_config("ai_draw.api_url", "https://api.xingzhige.com/API/DrawOne/")
            default_prompt = self.get_config("ai_draw.default_prompt", "jk")
            timeout = self.get_config("ai_draw.timeout", 30)

            # 处理人设描述词
            if prompt.lower() in ["self", "自己", "你自己", "你"]:
                bot_personality = global_config.personality.personality
                self_prompt = self.get_config("ai_draw.self_prompt", "")
                if not self_prompt:
                    self_prompt = "二次元少女 可爱 萌"
                    if "猫娘" in bot_personality or "猫" in bot_personality:
                        self_prompt = f"猫娘 猫耳 白发 {self_prompt}"
                prompt = self_prompt
                logger.info(f"使用人设描述词: {prompt}")

            # 换风格：从缓存获取
            if change_style:
                next_image = get_next_unsent_image(chat_id)
                if next_image:
                    img_data, idx = next_image
                    img_url = img_data.get("url")
                    if img_url:
                        await send_api.custom_to_stream("imageurl", img_url, chat_id)
                        cache = get_cached_images(chat_id)
                        sent_count = len(cache["sent_indices"]) if cache else 0
                        total = len(cache["images"]) if cache else 0
                        logger.info(f"换风格：发送缓存图片 [{sent_count}/{total}]")
                        return {"success": True, "message": f"已发送第{sent_count}张图片，还剩{total - sent_count}张可换"}
                else:
                    # 缓存用完，重新生成
                    logger.info("缓存图片已用完，重新生成")

            # 使用默认描述词
            if not prompt or not prompt.strip():
                prompt = default_prompt

            logger.info(f"开始AI绘图，描述词: {prompt}")

            # 调用API
            encoded_prompt = urllib.parse.quote(prompt)
            full_api_url = f"{api_url}?prompt={encoded_prompt}"

            async with aiohttp.ClientSession() as session:
                async with session.get(full_api_url, timeout=timeout) as response:
                    if response.status != 200:
                        return {"success": False, "message": f"API请求失败: {response.status}"}

                    data = await response.json()
                    if data.get("code") != 200:
                        return {"success": False, "message": f"API错误: {data.get('msg', '未知')}"}

                    images = data.get("data", [])
                    if not images:
                        return {"success": False, "message": "API返回空图片列表"}

                    logger.info(f"API返回 {len(images)} 张图片")

                    # 选择最佳图片
                    best_img, best_idx = select_best_image(prompt, images)

                    # 缓存所有图片
                    cache_images(chat_id, images, prompt, best_idx)

                    # 发送图片
                    img_url = best_img.get("url")
                    if img_url:
                        await send_api.custom_to_stream("imageurl", img_url, chat_id)
                        remaining = len(images) - 1
                        logger.info(f"AI绘图成功，描述词: {prompt}，还有{remaining}张其他风格")

                        result_msg = f"已生成图片（描述词: {prompt}）"
                        if remaining > 0:
                            result_msg += f"，还有{remaining}张其他风格可选"
                        return {"success": True, "message": result_msg}
                    else:
                        return {"success": False, "message": "图片URL为空"}

        except Exception as e:
            logger.error(f"AI绘图出错: {e}")
            return {"success": False, "message": f"绘图出错: {str(e)}"}
