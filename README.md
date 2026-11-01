# 大肥鱼 B站浏览分享

一个运行在 AstrBot 上的 QQ 私聊视频分享插件：搜索或读取 DSH 观看笔记，用当前聊天人格分享视频并表达看法；用户接着聊时，自动通过 BiliRead 补充字幕摘要，再继续对话。

支持 NapCat、SnowLuma 等接入 AstrBot 的 OneBot v11 协议端。本插件不负责 QQ 登录，也不会安装或运行第二个 QQ 客户端。

## 功能

- **自然分享**：介绍视频后顺口说自己的感受、吐槽或观点，沿用当前人格，不强制完整摘要。
- **两种来源**：`local` 自行搜索视频；`dsh` 使用已导入的 dsh-bili-scroll 观看笔记。
- **视频追问**：语义判断或引用推送消息，调用已启用的 BiliRead，先读再答；重复追问复用缓存。
- **历史查询**：自然语言调用 `feiyu_bili_history` 查询 DSH 观看笔记。
- **主动分享保护**：北京时间01—10点静默，每天最多3条，成功推送间隔至少120分钟，最多连续2条未回复；本人聊天后5分钟内不主动发送。
- **可靠性**：持久去重，发送结果未知时停止自动重试，QQ离线时暂停自动选片。

只面向配置的本人QQ私聊。不提供群聊推送、评论、点赞、投币、关注、私信或账号运营功能。

## 目录结构

```text
astrbot_plugin_feiyu_bili/
├── main.py                 # AstrBot 插件入口与对话接入
├── core/                   # 插件运行模块
│   ├── __init__.py         # Python 包标识
│   ├── engine.py           # 选片、生成分享及发送流程
│   ├── bili.py             # B站只读接口与字幕获取
│   ├── asr.py              # 可选音频转写
│   ├── followup.py         # 视频追问关联及读取缓存
│   ├── history.py          # DSH 观看记录查询
│   └── state.py            # 分享状态与持久化
├── _conf_schema.json       # 插件配置项
├── metadata.yaml           # AstrBot 插件元信息
├── requirements.txt        # Python 依赖
├── README.md               # 安装、配置和使用
├── CHANGELOG.md            # 更新记录
├── NOTICE                  # 第三方来源与授权声明
├── docs/                   # 可选功能接入文档
├── tools/                  # 笔记导入导出辅助工具
└── tests/                  # 自动化测试
```

根目录只保留 `main.py` 作为 Python 入口，其余运行模块位于 `core/`，由入口通过相对导入加载。`docs/`、`tools/` 和 `tests/` 分别存放说明、可选脚本和测试。

## 安装

要求 AstrBot **4.29.0 或更新版本**、已连通的 OneBot v11 QQ 账号，以及支持当前人格和工具的聊天模型。本次验证环境为 AstrBot 4.29.3；未来版本的内部接口变更可能需要适配。

1. 将此仓库上传到自己的 GitHub，在 AstrBot 插件页使用仓库URL安装；也可将仓库内容放到 AstrBot 的 `data/plugins/astrbot_plugin_feiyu_bili/` 后重载。
2. 在插件配置中填写 `owner_qq`，选择模型或保持跟随私聊。
3. 用本人QQ私聊机器人发送 `/肥鱼B站 状态`，绑定真实会话。
4. 先发 `/肥鱼B站 预览` 检查效果，再发 `/肥鱼B站 开启`。

不要把整个仓库放到 AstrBot 的“表情包导入”中；这是功能插件。安装依赖声明在 `requirements.txt`，不锁定或降级 AstrBot 核心依赖。

## 配置

所有项目在 AstrBot 插件配置界面填写，字段定义见 `_conf_schema.json`。仓库不含运行时账号、Cookie或API Key。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `owner_qq` | 空 | 本人QQ号，必填 |
| `enabled` | `false` | 启动时默认是否主动分享；私聊开启/关闭命令会持久保存状态 |
| `provider_id` | 空 | 选片/分享使用的模型ID，留空跟随绑定私聊 |
| `source_mode` | `local` | `local` 搜索；`dsh` 读取已同步笔记 |
| `keywords` | 美食、趣闻、轻度游戏 | 搜索兴趣，DSH来源不按这些词重新搜索 |
| `proxy` | 空 | 容器可访问的HTTP代理；空为直连，不是订阅链接 |
| `bilibili_cookie` | 空 | 可选B站Cookie，不会绕过B站权限或风控 |
| `asr_enabled` | `true` | 本地搜索无字幕时，短视频可尝试音频转写 |
| `asr_source_id` | `siliconflow` | 已有AstrBot硅基流动来源ID，非模型ID |
| `check_interval_minutes` | `60` | 检查周期，最少15分钟，不保证精确整点推送 |
| `preview_on_start` | `false` | 启动后自动生成一次不发送的诊断预览，可能产生费用 |
| `followup_enabled` | `true` | 已推送视频的追问自动读取 |
| `followup_lookback_hours` | `24` | 语义关联时间窗，1—168小时 |
| `followup_timeout_seconds` | `60` | BiliRead读取超时，10—120秒 |

更改插件配置后重载。若使用容器代理，`127.0.0.1` 指容器自身；请填写容器能够访问的实际代理地址。

## 私聊命令

| 命令 | 用途 |
|---|---|
| `/肥鱼B站 状态` | 绑定本人会话、查看状态 |
| `/肥鱼B站 预览` | 真实读取并调用模型，返回预览，不记录为主动分享 |
| `/肥鱼B站 今天` | 查询当天DSH笔记 |
| `/肥鱼B站 开启` | 开启主动分享 |
| `/肥鱼B站 关闭` | 关闭主动分享 |
| `/肥鱼B站 确认未送达` | 人工确认QQ没收到后，解除未知发送保护 |

预览仍可能消耗模型和ASR额度。普通私聊重置连续未回复计数，控制命令不重置。平台返回发送成功不代表用户已经阅读；不要在发送结果未知时直接删除状态库。

## 接着聊视频：BiliRead

另外安装 [BiliRead](https://github.com/SodaCodeSave/astrbot_plugin_biliread)，按其说明配置B站凭据和摘要模型，并在当前人格能力里启用 `bilibili_read` 工具。没有安装或无权限时，本插件不会强行读取。

成功推送后，可以说“刚才那个视频的观点你赞同吗？”，也可以引用原推送消息、提供BV号再问。系统先判断话题，调用BiliRead，再让当前聊天模型结合资料回答；无关聊天不触发。语义判断会产生一次额外的小型模型请求。

默认对最近24小时、保留的12条成功分享做语义关联。明确BV/引用可匹配列表中较早的分享；升级前只兼容恢复最后一条成功推送。预览不进入此列表。

成功摘要缓存24小时，失败冷却5分钟。首次读取可能较慢；无字幕或失败时保留原笔记，不假装知道未取得的细节。BiliRead提供的是字幕摘要，**不是画面识别，也不保证包含完整视频细节**。当前插件适配了BiliRead v1.2.0。

## 可选：接入 DSH 笔记

将 `source_mode` 改为 `dsh`，配合 `tools/` 下的笔记导出、导入工具使用。
完整操作见 [DSH 观看笔记接入](docs/dsh-notes.md)。

## 本地搜索与可选ASR

`local` 模式流程：关键词搜索 → 模型选片 → 字幕优先 → 可选短视频音频转写 → 当前人格分享。

ASR要求系统或容器内有 `ffmpeg`。复用已有硅基流动来源，地址必须为 `https://api.siliconflow.cn/v1`，模型为 `FunAudioLLM/SenseVoiceSmall`。只对不超过10分钟的视频尝试；音轨访问失败、超限或转写失败时退回标题简介。音频会上传给配置的ASR服务，可能计费。

连接建立失败时，ASR会用公共HTTPS DNS查询官方域名并直连重试一次，保持原域名、SNI和证书验证，不修改系统DNS。来源和实现细节见 `core/asr.py`。

## 数据与隐私

数据保存在 AstrBot 的 `plugin_data/astrbot_plugin_feiyu_bili/`，包括 `state.db`（会话绑定、分享记录、字幕及追问缓存）和 `viewing.db`（DSH笔记）。这些数据库不应上传GitHub。改变 `owner_qq` 会清理原用户会话、最近分享关联和详细摘要缓存。

本插件不直接写入LivingMemory或其他长期记忆插件的私有数据库。外部标题、笔记、字幕和摘要都只作为资料，不作为指令。禁用或卸载插件即可停止新增自动分享任务。

## 开发与验证

```console
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

测试使用临时数据库、模拟模型和发送接口，不发QQ消息、不需要真实密钥。当前48项回归覆盖推送限制、去重、历史、ASR边界、话题关联、缓存、权限和失败降级。运行时仍需要AstrBot及正确的B站/模型网络环境。

## 来源与发布

WBI签名与搜索逻辑参考 [SurfCore](https://github.com/Mieksido/surfcore)，具体提交与MIT声明见 [NOTICE](NOTICE)，发布时请保留。BiliRead独立安装，本仓库不包含其源代码。DSH笔记来自用户自行部署的 [dsh-bili-scroll](https://github.com/c1overzz/dsh-bili-scroll)。

上传自己的GitHub仓库后，可在 `metadata.yaml` 中补充真实 `repo` URL。原创部分的整体开源许可证由作者选择，仓库目前仅附带需保留的第三方授权声明。
