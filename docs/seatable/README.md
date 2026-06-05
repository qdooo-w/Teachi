# SeaTable 邮箱验证注册系统配置指南

本配置文档适用于系统的注册邮箱验证模块，指导如何搭建配套的 SeaTable 表格、邮箱发信自动化规则，以及后端 `.env` 环境变量的配置。

---

## 1. SeaTable 表格结构 (Table Schema)

您需要在 SeaTable 数据库（Base）中新建一张子表（例如命名为 `user_registration`），用于存储验证码及激活状态。该表需建立以下列：

| 列名 (名称) | 列类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- |
| `email` | 文本 (Text) | 用户注册填写的邮箱地址 | `user@example.com` |
| `code` | 文本 (Text) | 系统生成的随机验证激活码（通常为 UUID 或 6 位数字） | `d3b07384d113edec` |
| `status` | 单选 (Single Select) | 注册状态：<br>• `pending` (待处理/已发信)<br>• `registered` (已设置密码完成注册)<br>• `expired` (链接超时失效) | `pending` |
| `expires` | 日期/时间 (Date/Time) | 激活链接过期失效时间（建议为 ISO 8601 带时区格式） | `2026-06-05T22:20:00+00:00` |

> [!TIP]
> 建议将 `email` 和 `code` 列设置为非空。

---

## 2. 邮箱自动化规则配置 (Email Automation Setup)

本系统不再需要用户访问外部的 SeaTable 表单，用户直接在系统内输入邮箱，后端接收后会通过 API 写入 SeaTable 并自动触发以下规则发送激活邮件。

### 步骤一：配置“生成验证码与截止时间”的脚本规则
1. 进入 SeaTable 数据库，点击右上角的 **自动化规则 (Automation Rules)**。
2. 新增一条自动化规则：
   * **规则名称**：生成注册码及失效时间
   * **触发条件 (Trigger)**：`当向表中添加新行时 (When a new row is added)`
   * **执行动作 (Action)**：`运行 Python 脚本 (Run Python Script)`。
3. 在脚本中粘贴以下逻辑，自动生成随机激活码并设置 10 分钟后过期：
   ```python
   import datetime
   import uuid
   from seatable_api import Base

   # 初始化 Base（SeaTable 会自动注入 context）
   base = Base(context.api_token, context.server_url)
   base.auth()

   # 获取新增行的 ID
   row_id = context.event['row']['_id']

   # 计算 10 分钟后的过期时间 (UTC)
   now = datetime.datetime.now(datetime.timezone.utc)
   expires_dt = now + datetime.timedelta(minutes=10)
   expires_str = expires_dt.isoformat()

   # 生成激活码
   code = uuid.uuid4().hex

   # 更新数据
   base.update_row(context.event['table_name'], row_id, {
       'code': code,
       'status': 'pending',
       'expires': expires_str
   })
   ```

### 步骤三：配置“自动发送激活邮件”规则
1. 新增第二条自动化规则：
   * **规则名称**：发送激活确认邮件
   * **触发条件 (Trigger)**：`当某些列的数据发生变化时 (When columns change)`，监听 `code` 列。
   * **执行条件 (Condition)**：`status` 列的值为 `pending` 且 `code` 列不为空。
   * **执行动作 (Action)**：`发送邮件 (Send Email)`。
2. 配置发信账号：
   * 在弹窗中绑定发送账号（使用您的 SMTP 发信账号，如 NJU 邮箱、腾讯邮箱等）。
3. 编写邮件模版：
   * **收件人**：选择当前行的 `email` 列。
   * **主题**：`您的 Learnova 账号激活链接`
   * **邮件正文** (支持 Markdown / HTML)：
     ```html
     你好，感谢注册 Learnova！

     请点击下方链接完成邮箱验证，并设置您的账户密码（链接 10 分钟内有效）：
     http://your-backend-host/auth/verify?code={code}

     若非本人操作，请忽略此邮件。
     ```
     *(请将 `your-backend-host` 替换为您真实的后端 API 服务域名)*

---

## 3. 后端 `.env` 配置文件

为了让系统后端能够读取 SeaTable 并进行权限映射，您需要在 `learnova/backend` 同级目录下的 `.env` 文件中配置以下变量：

```env
# ==================== SeaTable 注册验证对接 ====================
# SeaTable 服务器主地址
SEATABLE_SERVER_URL=https://table.nju.edu.cn/

# 具有读写该表权限的 SeaTable App API Token
SEATABLE_API_TOKEN=c0f7db062beaa87312dfec0880b98a206b53f1e5

# 对应 Base 的 Base UUID (从表格后台 API 文档中获取)
SEATABLE_BASE_UUID=a674d1c6-3e1e-4136-a40d-9a9ea9f17180

# 表格名称
SEATABLE_TABLE_NAME=user_registration

# 各列字段的数据库映射名
SEATABLE_COLUMN_EMAIL=email
SEATABLE_COLUMN_CODE=code
SEATABLE_COLUMN_STATUS=status
SEATABLE_COLUMN_EXPIRES=expires

# ==================== 接口与重定向配置 ====================
# 后端发出的临时 JWT Token 的过期时效 (单位：分钟)，默认为 5 分钟
TEMP_TOKEN_EXPIRE_MINUTES=5

# 前端基础 URL 地址，用于 verify 后的重定向
FRONTEND_BASE_URL=http://localhost:5173

# 允许注册的邮箱后缀白名单（多个域名用逗号分隔，留空表示允许任意邮箱）
ALLOWED_EMAIL_DOMAINS=nju.edu.cn,smail.nju.edu.cn
```
