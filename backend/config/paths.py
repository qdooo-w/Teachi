import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]#项目的根目录路径，基于当前文件的位置向上两级

DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "project.db"))#数据库文件路径，默认为项目根目录下的 data/project.db

SKILL_STORAGE_DIR = os.getenv("SKILL_STORAGE_DIR", str(BASE_DIR / "data" / "skills"))#技能存储目录路径，默认为项目根目录下的 data/skills，用于存放技能相关的文件和资源
