"""
图片生成工具

用于生成歌曲列表等图片
"""

import os
import base64
from typing import List, Optional

try:
    import io
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from src.common.logger import get_logger

logger = get_logger("entertainment_plugin.image_generator")


def generate_music_list_image(
    music_list: List[dict],
    search_keyword: str,
    source_name: str = ""
) -> Optional[str]:
    """
    生成歌曲列表图片

    Args:
        music_list: 歌曲列表
        search_keyword: 搜索关键词
        source_name: 音乐源名称

    Returns:
        base64 编码的图片，失败或 PIL 不可用返回 None
    """
    if not PIL_AVAILABLE:
        logger.warning("[ImageGen] PIL未安装，无法生成列表图片")
        return None

    try:
        # 查找支持中文的字体
        chinese_font_paths = [
            # Windows 常用字体
            r"C:\\Windows\\Fonts\\msyh.ttc",
            r"C:\\Windows\\Fonts\\msyh.ttf",
            r"C:\\Windows\\Fonts\\msyhbd.ttf",
            r"C:\\Windows\\Fonts\\simhei.ttf",
            r"C:\\Windows\\Fonts\\simsun.ttc",
            r"C:\\Windows\\Fonts\\simsun.ttf",
            # Linux Noto CJK fonts
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            # WenQuanYi fonts
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            # Droid fonts
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
        ]

        font_path = None
        # 先按常见路径查找
        for path in chinese_font_paths:
            try:
                if os.path.exists(path):
                    font_path = path
                    logger.info(f"[ImageGen] 找到中文字体: {path}")
                    break
            except Exception:
                continue

        # 如果还没找到，在 Windows 上扫描字体目录
        if not font_path and os.name == 'nt':
            try:
                windows_fonts_dir = os.path.join(
                    os.environ.get('WINDIR', r"C:\\Windows"), 'Fonts'
                )
                if os.path.isdir(windows_fonts_dir):
                    for fname in os.listdir(windows_fonts_dir):
                        lower = fname.lower()
                        if any(k in lower for k in (
                            'msyh', 'simhei', 'simsun', 'noto',
                            'yahei', 'pingfang', 'uming', 'wqy'
                        )):
                            candidate = os.path.join(windows_fonts_dir, fname)
                            if os.path.exists(candidate):
                                font_path = candidate
                                logger.info(
                                    f"[ImageGen] 在 Windows 字体目录找到中文字体: "
                                    f"{candidate}"
                                )
                                break
            except Exception as e:
                logger.debug(f"[ImageGen] Windows 字体扫描失败: {e}")

        if not font_path:
            logger.warning("[ImageGen] 未找到支持中文的字体，无法生成图片列表")
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
        draw.text(
            (padding, 70),
            f"找到 {len(music_list)} 首歌曲，输入 /choose 序号 来选择",
            font=small_font,
            fill='white'
        )

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
            draw.text(
                (padding + 50, y + 40),
                f"{singer} - {album}",
                font=small_font,
                fill='#666666'
            )

            y += item_height

        # 绘制底部
        draw.rectangle([0, height - footer_height, width, height], fill='#333333')
        draw.text(
            (padding, height - 30),
            "提示: 使用 /choose <序号> 选择歌曲",
            font=small_font,
            fill='white'
        )

        # 转换为 base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        logger.info(f"[ImageGen] 成功生成歌曲列表图片，共 {len(music_list)} 首歌")
        return img_base64

    except Exception as e:
        logger.error(f"[ImageGen] 生成歌曲列表图片失败: {e}", exc_info=True)
        return None


def generate_music_list_text(
    music_list: List[dict],
    search_keyword: str,
    source_name: str = ""
) -> str:
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
