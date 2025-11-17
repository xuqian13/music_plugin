"""功能模块"""

from .image_module import RandomImageAction, RandomImageCommand
from .news_module import News60sTool, TodayInHistoryTool, NewsCommand, HistoryCommand
from .music_module import MusicCommand, ChooseCommand, QuickChooseCommand

__all__ = [
    # 图片模块
    'RandomImageAction',
    'RandomImageCommand',
    # 新闻模块
    'News60sTool',
    'TodayInHistoryTool',
    'NewsCommand',
    'HistoryCommand',
    # 音乐模块
    'MusicCommand',
    'ChooseCommand',
    'QuickChooseCommand',
]
