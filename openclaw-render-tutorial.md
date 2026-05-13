# 📱 OpenClaw + Phone：让微信AI帮你操作手机（Render部署版）

> 简版教程：在已有的 OpenClaw + 微信 基础上，接入手机控制能力
> 无需云服务器，免费部署到 Render

---

## 🔗 最终效果

```
微信发消息 → OpenClaw → MCP调用 → phone云端(Render) → WebSocket → 你的手机
```

AI 可以帮你在手机上点外卖、回消息、截图分析，你只需要在微信里说就行。

---

## 📋 前置条件

- ✅ 已有 OpenClaw 运行环境
- ✅ 已接通微信（cyberboss）
- ✅ 一台 Android 手机
- 🆕 需要一个豆包视觉模型 API Key（[点这里申请](https://console.volcengine.com/ark)）
- 🆕 [Render 账号](https://render.com)（免费注册）

---

## 第一步：部署 Phone 云端服务 ☁️

### 1.1 Fork 仓库

打开 [phone 仓库](https://github.com/chloemeadow0-code/phone)，点击右上角 **Fork** 到自己的 GitHub

### 1.2 部署到 Render

1. 登录 [Render](https://dashboard.render.com)
2. 点击 **New +** → **Web Service**
3. 选择 **Build and deploy from a Git repository**
4. 连接你的 GitHub，选择刚 Fork 的 `phone` 仓库
5. 填写配置：

| 配置项 | 填什么 |
|--------|--------|
| **Name** | 随便取，比如 `my-phone-service` |
| **Region** | 选离你近的（如 Singapore） |
| **Branch** | `main` |
| **Runtime** | **Docker** |
| **Instance Type** | **Free** |

6. 添加环境变量：

| Key | Value |
|-----|-------|
| `ARK_API_KEY` | 你的豆包视觉模型 API Key |

7. 点击 **Create Web Service**，等待部署完成（约2-3分钟）

### 1.3 拿到公网地址

部署完成后，Render 会分配一个域名，比如：

```
https://my-phone-service.onrender.com
```

> 💡 Render 免费版服务会在 15 分钟无请求后休眠，首次唤醒需要约 30-60 秒。如果介意可以升级付费版（$7/月）保持常驻。

---

## 第二步：手机连接 📱

### 2.1 安装 Portal App

前往 [Mobilerun Portal Releases](https://github.com/nicepkg/mobilerun/releases) 下载最新 APK 安装

### 2.2 开启无障碍权限

手机 **设置 → 无障碍 → 找到 Portal → 开启**

### 2.3 连接服务器

打开 Portal App，服务器地址填：

```
wss://你的服务名.onrender.com/ws
```

点击连接，看到「已连接」✅ 就OK了

> 💡 浏览器访问 `https://你的服务名.onrender.com/status` 可以确认手机是否在线

---

## 第三步：OpenClaw 接入 MCP 🤖

### 3.1 安装 MCP 插件

如果还没装 OpenClaw 的 MCP 插件，参考：
> https://github.com/lunarpulse/openclaw-mcp-plugin

### 3.2 添加 Phone 的 MCP SSE 地址

在 OpenClaw 的 MCP 配置中，添加远程 SSE 服务：

```
SSE 地址：https://你的服务名.onrender.com/mcp/sse
```

保存后重启 OpenClaw。

### 3.3 验证连接

在微信里给AI发：

> "帮我截个手机屏幕看看现在在什么页面"

如果AI成功调用 `phone_analyze_screen` 并返回结果，说明全部打通了 🎉

---

## 🛠️ 可用能力速查

| 能力 | 对应工具 | 微信里怎么说 |
|------|---------|-------------|
| 截图分析 | `phone_analyze_screen` | "帮我看看手机现在什么页面" |
| 点击按钮 | `phone_tap_by_description` | "帮我点搜索框" |
| 输入文字 | `phone_input_text` | "帮我输入古茗" |
| 打开应用 | `phone_launch_app` | "帮我打开美团" |
| 滑动屏幕 | `phone_swipe` | "往下滑一下" |
| 按返回键 | `phone_press_back` | "按一下返回" |

---

## ⚠️ 安全提醒

- **不要公开你的 MCP SSE 地址**，任何人拿到都能控制你的手机
- 不用的时候断开 Portal 连接
- 不要让AI操作银行/支付类应用
- 建议在 phone 服务的 `ws_endpoint` 里加 token 验证

---

## 🔧 常见问题

**Q: Render 部署失败？**
→ 确认 Runtime 选的是 **Docker**，仓库里有 Dockerfile 会自动识别

**Q: "No phone connected"**
→ 手机端 Portal App 没连上，检查 wss 地址是否正确（注意是 `wss://` 不是 `ws://`）

**Q: 首次连接很慢？**
→ Render 免费版会休眠，首次唤醒需要 30-60 秒，等一下就好

**Q: 视觉分析报错？**
→ 检查 Render 环境变量里的 `ARK_API_KEY` 是否正确配置

**Q: OpenClaw 调不到 phone 工具？**
→ 浏览器直接访问 `https://你的服务名.onrender.com/mcp/sse`，应该能看到 SSE 流

**Q: 免费版够用吗？**
→ 日常玩完全够用。只是15分钟不用会休眠，每次唤醒等几十秒。如果想要 24 小时在线，Render 付费版 $7/月

---

> 📖 完整教程见 [phone 仓库 README](https://github.com/chloemeadow0-code/phone)
> 
> 💛 灵感来源：想让 AI 帮老婆点奶茶
