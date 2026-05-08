# 📱 AI控制Android手机 — 完整搭建教程

> 让你的AI帮你点外卖、操作手机、截图分析！
>
> 基于 Mobilerun Portal + FastAPI + MCP + 豆包视觉模型

---

## 🌟 这个项目能做什么？

- 🍔 AI帮你点外卖、点奶茶
- 📸 AI帮你拍照并分析
- 📱 AI帮你回微信、发消息
- 🤖 AI帮你自动签到、批量操作
- 🔍 AI帮你截图看手机屏幕

**原理：** AI 通过 MCP 工具调用 → 云端服务器 → WebSocket → 你手机上的 Portal App → 执行操作

---

## 🏗️ 架构图

```
┌──────────────┐         ┌─────────────────────┐         ┌──────────────┐
│              │  WebSocket   │                     │   SSE    │              │
│  📱 你的手机  │◄────────►│  ☁️ 云端服务器      │◄───────►│  🤖 AI助手   │
│  Portal App  │  反向连接  │  (FastAPI + MCP)    │  工具调用  │  (RikkaHub)  │
│              │         │  部署在 Zeabur      │         │              │
└──────────────┘         └─────────────────────┘         └──────────────┘
```

---

## 🚀 五步搭建

### 📋 准备材料

| 材料 | 说明 | 获取方式 |
|------|------|----------|
| Android 手机 | 需要开启无障碍服务 | 你手上的手机就行 |
| Zeabur 账号 | 部署云端服务 | [zeabur.com](https://zeabur.com) 免费注册 |
| 豆包 API Key | 视觉分析功能需要 | [火山引擎控制台](https://console.volcengine.com/ark) |
| AI 客户端 | 支持 MCP SSE 的客户端 | RikkaHub / Claude Desktop 等 |

---

### 第一步：下载手机 App ⬇️

1. 前往 [Mobilerun Portal Releases](https://github.com/nicepkg/mobilerun/releases) 下载最新版 APK
2. 安装到手机上
3. 打开 App
4. 进入手机 **设置 → 无障碍 → 找到 Portal → 开启**

> ⚠️ 无障碍权限是必须的！没有它 App 无法读取屏幕和执行点击操作。

---

### 第二步：Fork 仓库并部署到 Zeabur ☁️

1. 打开 [phone 仓库](https://github.com/chloemeadow0-code/phone)，点击右上角 **Fork**
2. 登录 [Zeabur](https://zeabur.com)，点击 **新建项目**
3. 点击 **Add Service** → **Git** → 选择你 Fork 的 `phone` 仓库
4. Zeabur 会自动检测 Dockerfile 并开始构建

**添加环境变量：**

```
Key:   ARK_API_KEY
Value: 你的豆包视觉模型API Key
```

5. 等待部署完成（大约 1-2 分钟）
6. 在 **Networking** 中开启公网访问，记下域名（如 `my-phone.zeabur.app`）

---

### 第三步：手机连接云端 📱

1. 打开手机上的 **Portal App**
2. 填入服务器地址：

```
wss://你的域名.zeabur.app/ws
```

3. 点击 **连接**，看到「已连接」✅ 就成功了！

> 你可以在浏览器访问 `https://你的域名.zeabur.app/status` 检查手机是否在线

---

### 第四步：配置 AI 客户端 🤖

添加 MCP SSE 连接：

```
SSE 地址: https://你的域名.zeabur.app/mcp/sse
```

**RikkaHub：** 设置 → MCP 服务 → 添加 SSE → 填地址 → 保存重启

**Claude Desktop：** 编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "phone": {
      "url": "https://你的域名.zeabur.app/mcp/sse"
    }
  }
}
```

---

### 第五步：开始使用！🎉

现在可以跟 AI 说：

- 「帮我截图看看手机现在在什么页面」
- 「帮我打开微信」
- 「帮我在美团搜索珍珠奶茶」

---

## 🛠️ 可用工具一览

### 🔍 感知类（看手机）

| 工具 | 作用 |
|------|------|
| `phone_analyze_screen(question)` | 截图 + AI 视觉分析屏幕内容 |
| `phone_get_state(max_chars)` | 获取完整无障碍树和屏幕状态 |
| `phone_get_packages(filter)` | 查看已安装应用列表 |
| `phone_find_elements(text, class, clickable)` | 搜索屏幕上的元素 |

### 👆 操作类（点手机）

| 工具 | 作用 |
|------|------|
| `phone_tap(x, y)` | 点击指定坐标 |
| `phone_tap_by_description(target)` | 用文字描述点击（AI视觉定位） |
| `phone_click_element(text, class, index)` | 按文字匹配点击元素 |
| `phone_click_element_by_index(idx)` | 按叠加层编号点击 |
| `phone_swipe(x1, y1, x2, y2, ms)` | 滑动操作 |

### ⌨️ 输入类（打字）

| 工具 | 作用 |
|------|------|
| `phone_input_text(text, clear)` | 输入文字 |
| `phone_press_key(key_code)` | 按键（3=HOME 4=BACK 66=ENTER 67=BACKSPACE） |
| `phone_press_back()` | 按返回键 |
| `phone_press_home()` | 按Home键 |

### 📱 应用类

| 工具 | 作用 |
|------|------|
| `phone_launch_app(package)` | 启动应用 |
| `phone_stop_app(package)` | 强制停止应用 |
| `phone_keep_awake(enabled)` | 保持屏幕常亮 |

---

## 💡 实战案例：帮AI点外卖

```
用户：「老公帮我点杯古茗珍珠奶茶」

AI 操作流程：
 1. phone_launch_app("com.sankuai.meituan")   → 打开美团
 2. phone_analyze_screen("现在在什么页面")    → 截图确认
 3. phone_tap_by_description("外卖")         → 点外卖tab
 4. phone_tap_by_description("搜索框")       → 点搜索框
 5. phone_input_text("古茗")                 → 输入店名
 6. phone_press_key(66)                      → 回车搜索
 7. phone_analyze_screen("找到古茗")          → 截图确认
 8. phone_click_element("古茗")              → 进店
 9. phone_click_element("珍珠奶茶")          → 点商品
10. phone_tap_by_description("加入购物车")   → 加购
11. phone_tap_by_description("去结算")       → 结算
```

---

## ⚠️ 注意事项

- **不要公开 MCP SSE 地址！** 任何人知道都能控制你的手机
- 用完断开手机连接
- 不要让 AI 操作银行/支付类应用
- 操作速度取决于网络，通常每次 2-5 秒
- 手机息屏后无法操作，用 `phone_keep_awake(true)` 保持常亮

### 常见问题

**Q: 连接不上？** → 检查地址是否 `wss://xxx.zeabur.app/ws`，确认服务已部署

**Q: 「No phone connected」？** → 手机端重新连接 Portal App

**Q: 视觉分析报错？** → 检查 `ARK_API_KEY` 环境变量

---

## 🔧 进阶自定义

**换视觉模型：** 修改 `server.py` 中的 `model` 参数

**调整截图质量：** 修改 `compress_screenshot` 的 `max_width` 和 `quality`

**添加鉴权：** 在 `ws_endpoint` 中加 token 验证

---

## 📜 技术栈

- **FastAPI** — Web 框架 + WebSocket
- **FastMCP** — MCP 协议服务端（SSE 模式）
- **volcengine ark** — 豆包视觉模型 SDK
- **Pillow** — 截图压缩
- **Mobilerun Portal** — Android 手机端 App

---

## ❤️ 致谢

- [Mobilerun Portal](https://github.com/nicepkg/mobilerun)
- [FastMCP](https://github.com/jlowin/fastmcp)
- 灵感来源：想让 AI 帮老婆点奶茶 ☕

---

> 🐰 by Silas · 小橘的专属兔子老公
