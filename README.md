# STM32CubeMX2 中文汉化工具

非官方社区工具，用于给 **STM32CubeMX2**（Electron/Theia）添加中文界面。

> 本项目与 STMicroelectronics 无隶属或背书关系，不包含 STM32CubeMX 本体。

## 功能

- 一键汉化 / 一键回滚
- 导出翻译表（CSV）
- 导入翻译表并更新词典
- 环境与安装检查

## 已验证

| 项目 | 版本 |
|------|------|
| STM32CubeMX2 | 1.1.1 |
| 工具 / 词典 | v0.1.0 |

## 快速开始

### 源码运行

```powershell
cd STM32CubeMX2-Chinese
python main.py
```

请先完全退出 STM32CubeMX2 再执行汉化。

### 打包 EXE

```powershell
python -m PyInstaller --onefile --name STM32CubeMX2-Chinese --add-data "dict/localization.json;dict" main.py
```

产物：`dist\STM32CubeMX2-Chinese.exe`（目标机器无需安装 Python）。

## 目录

| 路径 | 说明 |
|------|------|
| `main.py` | 菜单入口 |
| `core/` | 安装检测、字节替换、备份回滚、CSV 导入导出 |
| `dict/localization.json` | 内置默认词典 |
| `tools/` | 词典安全检查等辅助脚本 |

## 说明

- 只修改已解包的前端资源 `bundle.js`，并同步 `bundle.js.gz`
- 产品名（GPIO、Pack、MCU、FreeRTOS 等）保持英文
- 详细使用与翻译流程见 `docs/`（完善中）

## 免责声明

使用本工具修改第三方软件可能违反其许可协议，风险自负。建议仅用于个人学习与本地界面理解。
