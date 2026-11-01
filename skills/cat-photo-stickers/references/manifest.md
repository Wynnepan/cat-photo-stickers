# 逐张裁切与图片内叠字

先运行 `index`。`catalog` 指向该次索引生成的完整 `catalog.json`；所有路径以 manifest 所在目录为基准（catalog 内的照片路径由脚本写为绝对路径）。manifest 必须与 catalog 的全部照片一对一对应。

以下是单图结构示例，运行时使用 `--count 1`；文件夹有 16 张时需写满 16 条。

```json
{
  "catalog": "catalog/catalog.json",
  "icon": {"source": "/path/to/photos/cat-01.jpg", "crop": [160, 240, 960, 1040]},
  "items": [
    {
      "id": "01",
      "source": "/path/to/photos/cat-01.jpg",
      "caption": "不许撤回",
      "crop": [160, 240, 960, 1040],
      "text_box": [0.06, 0.74, 0.50, 0.94],
      "protected_regions": [[0.32, 0.07, 0.89, 0.49], [0.55, 0.49, 0.98, 0.72]],
      "text_style": "white"
    }
  ]
}
```

这是格式示例，不能不看照片就照抄坐标。

| 字段 | 含义 |
|---|---|
| `id` | 成品文件名，不带扩展名；1–64 位英文字母、数字、下划线或横线，大小写无关地唯一 |
| `source` | 原照片路径；相对路径从 manifest 所在目录解析；必须来自这次完整 catalog |
| `caption` | 非空短句，支持 `\n` 主动换行；超过 80 字拒绝，推荐 2–8 个汉字 |
| `crop` | **EXIF 旋正后的原照像素坐标** `[左,上,右,下]`，整数，右/下为切片边界；宽必须等于高且不越界 |
| `text_box` | **裁切后的成品坐标**，用 0–1 比例表示 `[左,上,右,下]`；文字整块放在其中，距边至少 2.5% |
| `protected_regions` | 裁切后成品中的猫脸、关键爪子/道具等区域，同样用 0–1 坐标。至少标一个猫脸区域；文字区域不可与任何一项重叠 |
| `text_style` | 可选；默认 `white` 纯白无描边；浅底用 `black` 纯黑无描边。仅用户要求描边时使用 `white-black` 或 `black-white` |

换算原图上某个点到裁切后坐标：`x' = (x - crop.left) / crop.width`，`y' = (y - crop.top) / crop.height`。只有在原照片观察并确定主体位置后才能填写。

文字区域定义的是安全排版矩形，不是硬性固定顶/底栏。脚本居中放置文字，按区域宽度换行、必要时缩小字号；最多三行，过小或放不下时报错。默认无描边；显式选择描边样式时描边计入排版尺寸。文字区域与保护区域重叠时，脚本直接拒绝，不自行猜测安全位置。

## 命令参数

- `index --photos DIR --out NEW_DIR`：递归扫描 JPEG、PNG、WebP、BMP、TIFF，生成联系表和 catalog（含输入根目录 `photos_root`）；损坏文件会记录，build 阶段要求先处理。自动跳过隐藏目录、`表情包结果`、`表情包结果-*`，以及带 `.cat-photo-stickers-output` 文件的结果目录。建议索引写入输入文件夹下 `.cat-photo-stickers/运行编号/catalog`。
- `build --manifest FILE --font FONT [--out NEW_DIR]`：导出；`--out` 可省略，默认在原照文件夹内创建 `表情包结果/`，存在则递增为 `表情包结果-02/` 等新目录。默认 `--count 16 --size 512`。
- `--count N`：实际要处理的照片数，1–128；必须同时匹配完整 catalog 和 manifest。
- `--size N`：正方形边长，128–2048。

裁切与文字由调用 skill 的 AI 逐张观察后设计，Python 脚本只负责确定性执行，不含自动猫脸识别或自动写文案。脚本不联网、不自动抠图、不重绘照片。

默认结果子目录中的 `source-map.json` 是本地追溯信息，含私人路径；不加入分享 ZIP，也不要上传 GitHub。分享包是 默认结果子目录中的 `stickers.zip`，其中包含 `stickers/*.png`、`cover.png`、`icon.png` 和 `captions.json`。

结果目录中的隐藏标记 `.cat-photo-stickers-output` 用于防止后续索引误扫成品，不加入分享 ZIP。旧版 catalog 未记录 `photos_root` 时，默认输出根目录退回到所有原照的共同父目录；建议重新索引以准确保留用户最初提供的文件夹。

## 封面与图标

每次 build 自动导出 1024×1024 的 `cover.png`（全套成品方形拼图）与 512×512 的 `icon.png`（无字原照裁切），四列预览也使用 `preview.png`。所有图片均用 PNG 编码。封面和图标加入 ZIP，预览和本地来源映射不加入 ZIP。

manifest 顶层可指定 `icon: {"source": "原照路径", "crop": [左,上,右,下]}`。来源必须是本套照片之一，裁切为 EXIF 旋正后原照中的有效正方形像素区域。调用 skill 时应根据照片选清楚的猫脸、填写此项；脚本兼容省略时退回第一张原照的裁切，但该退回不保证最佳猫脸构图。
