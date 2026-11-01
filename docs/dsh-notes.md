# DSH 观看笔记接入

`source_mode=dsh` 时，不需要在 AstrBot 中运行 DSH，也不会自行下载或转写推荐视频；从已导入的最近7天“挑中且有笔记”记录选片。后续被标为跳过的同一视频不再推荐。

仓库提供无私人服务器信息的手动导出/导入工具：

```console
python tools/export_notes.py --home <DSH的bili-duty目录> --output records.json
python tools/import_notes.py --input records.json --database <AstrBot插件数据目录>/astrbot_plugin_feiyu_bili/viewing.db
```

示例路径为占位符，请换成自己的路径。导出器只读取 `reports/*.md` 和 `seen.md` 中的笔记字段，不读取DSH配置、Cookie、私人记忆或聊天。导入按日期/BV新增或更新，不把本机删除视为云端删除。

本机与云端分开时，需要自行使用SSH/SCP或已有同步方式传输 `records.json`，再在云端执行导入；仓库不会自动创建Windows定时任务，也没有预置服务器或SSH密钥。原有的个人自动同步部署不属于公开插件包。

自然语言可问“今天刷了什么”“查一下某日期的视频”“之前那条视频讲了什么”。这些是观看笔记，不能据此声称看完或知道未记录的画面。


上述命令均在仓库根目录执行。返回 [主说明](../README.md)。
