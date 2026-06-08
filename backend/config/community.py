import os
from typing import Literal

from backend.config.env import env_int


CommunitySkillSort = Literal["popular", "newest", "most_liked"]

PAGE_DEFAULT_LIMIT = env_int(os.getenv("COMMUNITY_PAGE_DEFAULT_LIMIT"), 20)#社区技能分页默认限制，每页显示的技能数量，默认为20
PAGE_MAX_LIMIT = env_int(os.getenv("COMMUNITY_PAGE_MAX_LIMIT"), 100)#社区技能分页最大限制，每页显示的技能数量，最大为100
SORT_DEFAULT: CommunitySkillSort = "popular"
SORTS: tuple[CommunitySkillSort, ...] = ("popular", "newest", "most_liked")#社区技能排序选项
