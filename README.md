# STM32CubeMX2 中文汉化工具

非官方社区工具，用于给 **STM32CubeMX2**（Electron/Theia）添加中文界面。

> 本项目与 STMicroelectronics 无隶属或背书关系，不包含 STM32CubeMX 本体。
> 使用本工具修改第三方软件可能违反其许可协议，风险自负，建议仅用于个人学习与本地界面理解。

[![Release](https://img.shields.io/github/v/release/P1nkDog/STM32CubeMX2-Chinese)](https://github.com/P1nkDog/STM32CubeMX2-Chinese/releases)
[![Check](https://img.shields.io/github/actions/workflow/status/P1nkDog/STM32CubeMX2-Chinese/check.yml)](https://github.com/P1nkDog/STM32CubeMX2-Chinese/actions)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-blue)](https://www.microsoft.com/windows)

## 功能特性

- 一键汉化 / 一键回滚
- 词典在线更新（从 GitHub 拉取最新词典）
- 软件更新（用默认浏览器打开 GitHub Releases 发布页）
- 导出翻译表（CSV）并导入更新词典
- 环境与安装检查
- 安全防护：自动备份、命中数校验、进程检测

## 效果预览

汉化后的 STM32CubeMX2 工程编辑界面：

![汉化后](docs/images/after.png)

## 已验证环境

| 项目 | 版本 |
|------|------|
| STM32CubeMX2 | 1.1.1 |
| 工具 / 词典 | v0.1.0 |

## 快速开始

### 方式一：下载 EXE（推荐）

1. 前往 [Releases 发布页](https://github.com/P1nkDog/STM32CubeMX2-Chinese/releases) 下载最新版 EXE。
2. **完全退出 STM32CubeMX2**（含系统托盘图标）。
3. 双击运行程序，主菜单选择 `2) 一键汉化`。
4. 启动 STM32CubeMX2 查看中文界面。想还原时再次运行并选择 `3) 一键回滚`。

### 方式二：源码运行

```powershell
cd STM32CubeMX2-Chinese
python main.py
```

需要 Python 3.11+（仅标准库，无第三方依赖）。

## 使用说明

### 交互菜单

| 选项 | 功能 |
|------|------|
| 1) 环境/安装检查 | 检测安装目录、运行进程、词典与汉化状态 |
| 2) 一键汉化 | 备份后替换 bundle.js 并同步 bundle.js.gz |
| 3) 一键回滚 | 从 .orig 备份恢复原版文件 |
| 4) 词典更新 | 从 GitHub 拉取最新词典（自动与本地版本比较） |
| 5) 软件更新 | 用默认浏览器打开 GitHub Releases 发布页 |
| 6) 高级 | 进入高级菜单（预览替换、导出/导入翻译表） |

高级菜单（主菜单选 6 进入）：

| 选项 | 功能 |
|------|------|
| 1) 预览替换（不写盘） | 只统计词典命中情况，不修改任何文件 |
| 2) 导出翻译表（含词典已有中文） | 扫描 bundle.js 生成 manual-translate.csv，供人工翻译 |
| 3) 导入翻译表并更新词典 | 读取 CSV 中填好的中文，更新词典后即可汉化 |
| 0) 返回主菜单 | 返回上级菜单 |

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-g, --path <目录>` | 指定 CubeMX2 安装根目录 |
| `--patch` | 执行汉化（免菜单） |
| `--rollback` | 一键回滚 |
| `--dry-run` | 只统计命中，不写盘 |
| `--doctor` | 环境/安装检查 |
| `--update-dict` | 从 GitHub 拉取最新词典并应用 |
| `--open-github` | 打开 GitHub Releases 发布页（软件更新） |
| `--export-csv` | 导出翻译表 |
| `--import-csv` | 导入翻译表并更新词典 |
| `--check-update` | 兼容旧参数，等价 `--update-dict` |
| `--version` | 显示版本号 |

## 更新

- **词典更新**（菜单 4 / `--update-dict`）：从 GitHub 拉取最新 `localization.json`，
  写入 EXE 旁（或 `%LOCALAPPDATA%`），汉化时自动优先使用。词典版本号变化即可检测到更新。
- **软件更新**（菜单 5 / `--open-github`）：打开 GitHub Releases 发布页，自行下载新版 EXE。

> 远程地址由 `core/dictionary.py` 中的 `GITHUB_REPO` 决定（当前：`P1nkDog/STM32CubeMX2-Chinese`）。

## 安全机制

- **自动备份**：汉化前将原文件备份为 `bundle.js.orig`（仅首次备份，不覆盖），可随时一键回滚。
- **命中数校验**：词典每条记录原文在 bundle.js 中的出现次数（expect），
  实际命中数不一致时安全跳过，防止 CubeMX2 升级后译文错位。
- **进程检测**：汉化/回滚前检测 STM32CubeMX2 是否在运行，避免写入被占用或覆盖。
- **只改前端资源**：仅修改 `bundle.js` 并同步 `bundle.js.gz`，不触碰可执行文件。
- **术语保留**：GPIO、DMA、NVIC、EXTI、SPI、CMSIS、Pack、MCU、FreeRTOS 等专有名词保留英文。

## 参与翻译

词典最开始是由 AI 大模型翻译的，为了更加精准的翻译，需要社区协作维护，
完整教程见：[docs/TRANSLATION.md](docs/TRANSLATION.md)。核心流程：

```
导出翻译表（CSV） -> 填写中文 -> 导入翻译表并更新词典 -> 汉化验证 -> 提交 Pull Request
```

## 项目结构

| 路径 | 说明 |
|------|------|
| `main.py` | 命令行入口与交互菜单 |
| `core/` | 核心库：安装检测、字节替换、备份回滚、CSV 导入导出、词典/软件更新 |
| `dict/localization.json` | 内置默认词典（1308 条映射） |
| `tools/check_dict.py` | 词典结构校验（CI 使用） |
| `tools/make_icon.py` | PNG 转 ICO 图标工具 |
| `tools/purge_unsafe_dict.py` | 清理词典中可能破坏 JS 的条目（本地开发用） |
| `tools/simulate_patch_safety.py` | 模拟替换安全性检查（本地开发用，需本机 bundle.js） |
| `icon/` | 程序图标 |
| `docs/` | 文档：翻译指南、效果截图 |
| `.github/workflows/check.yml` | CI：代码编译与词典结构校验 |

## 开发者指南

### 打包 EXE

```powershell
python -m PyInstaller --onefile --name STM32CubeMX2-Chinese --add-data "dict/localization.json;dict" --icon "icon/icon.ico" main.py
```

产物：`dist\STM32CubeMX2-Chinese.exe`（目标机器无需安装 Python）。

> 图标：`icon/icon.ico` 由 `tools/make_icon.py` 从 PNG 生成，换图标可运行
> `python tools/make_icon.py <图片.png>` 重新生成。

### 词典校验

```powershell
python tools/check_dict.py
```

提交 `dict/localization.json` 前建议先跑一遍；CI 也会自动执行。

## 常见问题

**Q: 汉化后部分界面还是英文？**
A: 正常。当前词典覆盖了 1308 条常见文本，未覆盖部分仍显示英文；
   欢迎参与翻译扩充（见「参与翻译」）。

**Q: 提示"未找到 STM32CubeMX2 安装目录"？**
A: 使用 `-g <安装目录>` 指定，或设置环境变量 `STM32CUBEMX2_PATH`。

**Q: 提示"STM32CubeMX2 正在运行"？**
A: 先完全退出 CubeMX2（含系统托盘），再执行汉化。

**Q: 杀毒软件报毒？**
A: PyInstaller 打包的单文件 EXE 偶发误报，可将程序加入杀毒软件白名单后使用。

**Q: CubeMX2 升级后汉化条目大量被跳过？**
A: 升级后原文出现次数变化，程序会安全跳过不匹配条目，等待词典更新适配新版本。

**Q: 汉化后想恢复原版？**
A: 运行程序选择 `3) 一键回滚`，或手动删除汉化产生的 `bundle.js.orig` 同名备份即可还原。
