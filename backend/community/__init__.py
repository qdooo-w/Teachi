"""
社区功能模块。

本模块包含社区技能广场、个人仓库、审核管理等功能的 API 路由和工具函数。

路由:
    - router: 社区技能广场路由 (/community)
    - library_router: 个人仓库路由 (/library)
    - router_owner: 技能管理员审核路由 (/owner)
    - router_admin: 系统管理员审核路由 (/admin)
"""

from backend.community.routes import router
from backend.community.library import router as library_router
from backend.community.admin import router_owner, router_admin

__all__ = ["router", "library_router", "router_owner", "router_admin"]
