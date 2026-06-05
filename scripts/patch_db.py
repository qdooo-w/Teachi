import re

with open("backend/db.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insert migration methods before setup_database
migration_methods = """    @staticmethod
    def _migrate_to_v2_pre(cursor: sqlite3.Cursor) -> None:
        cursor.execute("PRAGMA table_info(users)")
        if "role" not in {r["name"] for r in cursor.fetchall()}:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        
        cursor.execute("PRAGMA table_info(community_skills)")
        cs_cols = {r["name"] for r in cursor.fetchall()}
        if cs_cols and "admin_uuids" not in cs_cols:
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_created_at")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_downloads")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_owner")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_name")
            cursor.execute("ALTER TABLE community_skills RENAME TO community_skills_old")

    @staticmethod
    def _migrate_to_v2_post(cursor: sqlite3.Cursor) -> None:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='community_skills_old'")
        if not cursor.fetchone():
            return
            
        import json
        import uuid
        cursor.execute("SELECT * FROM community_skills_old")
        for row in cursor.fetchall():
            skill_id = row["id"]
            owner_uuid = row["owner_uuid"]
            admin_uuids = json.dumps([owner_uuid])
            
            cursor.execute(
                \"\"\"
                INSERT INTO community_skills 
                (id, owner_uuid, name, display_name, description, admin_uuids, likes, downloads, latest_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                \"\"\",
                (
                    skill_id, owner_uuid, row["name"], row.get("display_name"), row["description"],
                    admin_uuids, 0, row.get("downloads", 0), "1.0.0", row["created_at"], row["updated_at"]
                )
            )
            
            version_id = str(uuid.uuid4())
            cursor.execute(
                \"\"\"
                INSERT INTO community_skill_versions
                (id, skill_id, version, readme_md, changelog, tags, archive_path, size_bytes, downloads, source, status, submitted_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                \"\"\",
                (
                    version_id, skill_id, "1.0.0", "", "Auto-migrated version", "[]",
                    row.get("archive_path", ""), row.get("size_bytes", 0), row.get("downloads", 0),
                    None, "APPROVED", owner_uuid, row["created_at"]
                )
            )
        
        cursor.execute("DROP TABLE community_skills_old")

    def setup_database(self) -> None:"""

content = content.replace("    def setup_database(self) -> None:", migration_methods)

# 2. Add calls to pre/post in setup_database
setup_start = content.find("        with self.db_cursor() as cursor:")
after_cursor = content.find("\n", setup_start) + 1
content = content[:after_cursor] + "            self._migrate_to_v2_pre(cursor)\n" + content[after_cursor:]

executescript_pos = content.find("            cursor.executescript(schema)")
after_executescript = content.find("\n", executescript_pos) + 1
content = content[:after_executescript] + "            self._migrate_to_v2_post(cursor)\n" + content[after_executescript:]

# 3. Replace the community_skills schema string
old_schema_part = """            CREATE TABLE IF NOT EXISTS community_skills (
                id TEXT PRIMARY KEY,
                owner_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                description TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                license TEXT,
                compatibility TEXT,
                size_bytes INTEGER NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_community_skills_created_at ON community_skills(created_at);
            CREATE INDEX IF NOT EXISTS idx_community_skills_downloads ON community_skills(downloads);
            CREATE INDEX IF NOT EXISTS idx_community_skills_owner ON community_skills(owner_uuid);
            CREATE INDEX IF NOT EXISTS idx_community_skills_name ON community_skills(name);"""

new_schema_part = """            CREATE TABLE IF NOT EXISTS community_skills (
                id TEXT PRIMARY KEY,
                owner_uuid TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                description TEXT NOT NULL,
                admin_uuids TEXT NOT NULL DEFAULT '[]',
                likes INTEGER NOT NULL DEFAULT 0,
                downloads INTEGER NOT NULL DEFAULT 0,
                latest_version TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_versions (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL,
                readme_md TEXT DEFAULT '',
                changelog TEXT DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                archive_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING_ADMIN',
                submitted_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(skill_id, version),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (submitted_by) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_likes (
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (skill_id, user_uuid),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_comments (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_id TEXT,
                depth INTEGER NOT NULL DEFAULT 0,
                reply_to_uuid TEXT,
                likes INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (reply_to_uuid) REFERENCES users(uuid) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS community_comment_likes (
                comment_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (comment_id, user_uuid),
                FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_comment_reports (
                id TEXT PRIMARY KEY,
                comment_id TEXT NOT NULL,
                reporter_uuid TEXT NOT NULL,
                reason TEXT NOT NULL,
                detail TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                resolved_by TEXT,
                resolved_at REAL,
                created_at REAL NOT NULL,
                UNIQUE(comment_id, reporter_uuid),
                FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (reporter_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
                FOREIGN KEY (resolved_by) REFERENCES users(uuid) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS community_skill_contributors (
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'contributor',
                created_at REAL NOT NULL,
                PRIMARY KEY (skill_id, user_uuid),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_library_skills (
                id TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                description TEXT NOT NULL,
                readme_md TEXT DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                version TEXT NOT NULL,
                changelog TEXT DEFAULT '',
                source TEXT,
                community_skill_id TEXT,
                local_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS skill_review_logs (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                reviewer_uuid TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY (version_id) REFERENCES community_skill_versions(id) ON DELETE CASCADE,
                FOREIGN KEY (reviewer_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_community_skills_created_at ON community_skills(created_at);
            CREATE INDEX IF NOT EXISTS idx_community_skills_downloads ON community_skills(downloads);
            CREATE INDEX IF NOT EXISTS idx_community_skills_likes ON community_skills(likes);
            CREATE INDEX IF NOT EXISTS idx_community_skills_owner ON community_skills(owner_uuid);
            CREATE INDEX IF NOT EXISTS idx_community_skills_name ON community_skills(name);
            CREATE INDEX IF NOT EXISTS idx_community_versions_skill ON community_skill_versions(skill_id);
            CREATE INDEX IF NOT EXISTS idx_community_versions_status ON community_skill_versions(status);
            CREATE INDEX IF NOT EXISTS idx_community_versions_submitted ON community_skill_versions(submitted_by);
            CREATE INDEX IF NOT EXISTS idx_community_comments_skill ON community_skill_comments(skill_id);
            CREATE INDEX IF NOT EXISTS idx_community_comments_parent ON community_skill_comments(parent_id);
            CREATE INDEX IF NOT EXISTS idx_community_likes_skill ON community_skill_likes(skill_id);
            CREATE INDEX IF NOT EXISTS idx_comment_likes_comment ON community_comment_likes(comment_id);
            CREATE INDEX IF NOT EXISTS idx_comment_reports_comment ON community_comment_reports(comment_id);
            CREATE INDEX IF NOT EXISTS idx_library_skills_user ON user_library_skills(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_library_skills_community ON user_library_skills(community_skill_id);
            CREATE INDEX IF NOT EXISTS idx_review_logs_version ON skill_review_logs(version_id);
            CREATE INDEX IF NOT EXISTS idx_review_logs_reviewer ON skill_review_logs(reviewer_uuid);"""

content = content.replace(old_schema_part, new_schema_part)

# Remove legacy migration that modifies new community_skills
legacy_mig = """            cursor.execute("PRAGMA table_info(community_skills)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "archive_path" not in columns:
                cursor.execute(
                    "ALTER TABLE community_skills ADD COLUMN archive_path TEXT NOT NULL DEFAULT ''"
                )
            if "display_name" not in columns:
                cursor.execute("ALTER TABLE community_skills ADD COLUMN display_name TEXT")
            self._migrate_legacy_community_skill_bodies(cursor)"""
content = content.replace(legacy_mig, "")


with open("backend/db.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied.")
