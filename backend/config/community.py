import os
from typing import Literal

from backend.config.env import env_int


CommunitySkillSort = Literal["popular", "newest"]

PAGE_DEFAULT_LIMIT = env_int(os.getenv("COMMUNITY_PAGE_DEFAULT_LIMIT"), 20)#社区技能分页默认限制，每页显示的技能数量，默认为20
PAGE_MAX_LIMIT = env_int(os.getenv("COMMUNITY_PAGE_MAX_LIMIT"), 100)#社区技能分页最大限制，每页显示的技能数量，最大为100
SORT_DEFAULT: CommunitySkillSort = "popular"
SORTS: tuple[CommunitySkillSort, ...] = ("popular", "newest")#社区技能排序选项，默认按受欢迎程度排序，另一个选项是按最新发布排序
