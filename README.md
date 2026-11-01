# 猫咪原照表情包 · cat-photo-stickers

把本地文件夹里的 **16 张猫照，各自变成一张正方形表情包**。根据每张照片的神态配短句，文字**直接叠在照片里面**，避开猫脸和关键动作。

照片铺满正方形，不加白边或外置文案栏。每张照片单独裁切、配字和选位置，不用同一张照片凑成 16 张。默认导出 512×512 PNG，可调整大小和数量；每套额外生成正方形 PNG 封面和图标。所有交付图片均为 PNG 编码。

本仓库只做原照配字；线条简笔画是另一个独立技能。

## 下载与安装

GitHub 页面选择 **Code → Download ZIP**，解压进入本仓库根目录，然后运行：

```bash
python3 install.py
```

默认装到 `${CODEX_HOME:-~/.codex}/skills/cat-photo-stickers`。可通过 `--skills-dir /your/skills` 改位置。已安装同名技能时拒绝覆盖；更新前把旧目录移到 skills 之外备份后再安装。

依赖 Python 3.9+ 和 Pillow。推荐建虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/cat-photo-stickers/requirements.txt
```

Windows 使用 `.venv\Scripts\python.exe`。告诉 AI 使用这个 Python 的完整路径执行脚本。已有 Pillow 的 Python 环境可直接使用。技能需要宿主能查看本地图片并运行 Python，不需要图像生成服务或 API Key。

## 使用

安装后在新对话中调用；未发现新技能时重启宿主。提供实际照片文件夹路径，例如：

> 使用 $cat-photo-stickers，处理 /path/to/my-cat-photos 文件夹的 16 张照片。每张各做一张正方形表情包，文字嵌在照片里，避开猫脸，配字自然一点，输出预览和 ZIP。使用 Python /path/to/.venv/bin/python。

AI 会索引全部原照、逐张查看并设计文案、正方形裁切与画内文字位置，再由本地脚本执行和打包。照片只给一张试做时，只制作一张。

## 输出

- `stickers/`：逐张 PNG，默认 512×512。
- `preview.png`：四列预览，便于检查整批。
- `cover.png`：1024×1024 正方形封面，默认用整套成品拼图。
- `icon.png`：512×512 正方形图标，选原照猫脸独立裁切，无文字。
- `stickers.zip`：16 张 PNG、封面 PNG、图标 PNG 与文案清单，可直接分享。
- `source-map.json`：本地原照对应记录，含路径，不进入 ZIP。

默认输出位于**用户输入的照片文件夹下 `表情包结果/`**；再次导出使用 `表情包结果-02/` 等新版本目录，不覆盖原照或旧成品。索引、计划和 manifest 放在该输入目录内的 `.cat-photo-stickers/运行编号/` 隐藏工作目录。索引会自动排除隐藏目录、结果及版本目录和带输出标记的目录，避免下次将成品算进原照。默认文字无描边、无边框：深底用纯白字，浅底用纯黑字，逐张选择。字体由本地提供，最终仍需查看预览确认中文字形完整。

## 脚本与限制

```bash
.venv/bin/python skills/cat-photo-stickers/scripts/photo_stickers.py index \
  --photos /path/to/photos --out /path/to/photos/.cat-photo-stickers/run-01/catalog

.venv/bin/python skills/cat-photo-stickers/scripts/photo_stickers.py build \
  --manifest /path/to/photos/.cat-photo-stickers/run-01/manifest.json \
  --font /path/to/chinese-font.ttf
```

参数与逐张设计的 JSON 结构见 [格式说明](skills/cat-photo-stickers/references/manifest.md)。

AI 负责看图、文案、裁切和标记保护区域；脚本不含自动猫脸识别。脚本检查文字区域不与标记的猫脸/动作区域重叠，但标记是否准确需视觉复核。整批检查来源一一对应、数量一致，以及字节相同的重复文件。损坏文件先修复或重新提供；HEIC/RAW 先转换后索引。

正方形裁切可能舍去照片边缘或身体下部，优先保留表情与关键动作。它不会在原图外补画，也不自动抠图。通用 PNG 素材不代表已满足任何聊天平台表情商店的上架规格。

## 上传 GitHub

本目录可作为一个独立仓库根目录上传；不要上传外层 Bot 项目。代码包不包含用户猫照、成品或字体。照片、索引与成品保存在用户输入的本地照片文件夹中，不进入代码仓库。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试验证照片铺满正方形、文字在图内、脸部保护、一对一来源、坏数据拒绝、EXIF 方向和 ZIP 隐私边界。使用合成照片，无真实猫照。

## 来源与使用许可

本项目来源于维护者的个人猫咪表情包制作需求，由维护者提出需求与视觉偏好，借助 **OpenAI Codex** 辅助编写、迭代和测试代码。图片处理基于 Python 与 Pillow；它们各自的许可证独立适用。本仓库不包含用户原照、成品、个人路径、账号凭据或字体文件。

**仅限个人学习与非商业使用，禁止商业用途。** 未经维护者事先书面许可，不得将本项目用于付费服务、销售、商业产品集成、企业经营或商业推广，也不得利用本项目出售表情包或提供收费制作服务。修改或非商业再分发时必须保留来源与许可说明。

具体条款见 [LICENSE](LICENSE)。本项目公开源码，但不采用允许商用的 MIT 许可证。用户原照、字体与其他素材的权利仍归各自权利人，本许可不授予第三方素材权利。
