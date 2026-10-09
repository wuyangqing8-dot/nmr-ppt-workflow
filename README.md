# nmr-ppt-workflow

Windows 本地 Mnova/ChemDraw 氢谱归属审核与可编辑科研 PPT 工具，含 Codex 技能及个人默认绘图规则。

## 安装和调用

需要 Python 3.12、已安装并可正常使用的 ChemDraw、PowerPoint；直接读取 Mnova 时还需要 Mnova。谱线也支持 CSV/TXT/JSON。

1. 下载或克隆本仓库，双击 `install.bat` 安装 Python 依赖。
2. 在项目目录执行 `powershell -ExecutionPolicy Bypass -File .\install_skill.ps1`。脚本安装技能并保存当前项目路径，项目移动后重新运行。
3. 在 Codex 新会话使用 `$nmr-ppt-workflow`，提供结构、实验谱、参考 PPT 和溶剂。
4. 双击 `run.bat` 打开本地审核界面。

命令行示例：

```powershell
.\.venv\Scripts\python.exe -m app.main run --structure input_data/molecule.cdxml --experiment input_data/experiment.mnova --template input_data/reference.pptx --output outputs/new_task --solvent CDCl3
.\.venv\Scripts\python.exe -m app.main gui --task outputs/new_task/task.json
.\.venv\Scripts\python.exe -m app.main export --task outputs/new_task/task.json
```

Mnova 安装位置不在默认路径时设置 `MNOVA_EXE`。页号从 0 开始，必要时指定 `--experiment-page`、`--prediction-page`。外部预测 CSV 必须带原子映射；格式见 `examples/prediction_schema.csv`。实验积分格式见 `examples/integrals_schema.csv`。

## 默认绘图

- 先判断等效氢，每个环境只标一个代表原子。
- POSS 按用户指定分组习惯处理，跨分子先验证连接关系和成员，不能照搬原子 ID 或峰对应。
- Arial 16 pt、蓝色字母，靠近原子，在较空的位置按结构顺序排列。
- 不用指引线、问号和 g/h 互斥候选形式；有依据时选择最强推定对应，并在报告保留备选和理由。
- 字母直接放在真实峰上方，不附具体 ppm 数字。重叠环境可用组合字母。
- 默认不显示分子式文本框，分子式仍保存在任务数据中。
- CDCl₃、H₂O 等数字使用可编辑的原生下标。
- 每次导出检查 PowerPoint 渲染。详细规则见 [skill/SKILL.md](skill/SKILL.md)。

## 科研限制

自动建议和优先推定均需科研审核。删除问号或选择一种显示对应不等于确认。没有原子预测映射时不能编造预测位移或把普通实验峰称为原子预测。证据不足的环境保留未解决。原始积分不能修改，重叠信号不能人为拆成伪造实验峰。

PPT 标签为独立可编辑文本，结构保留原 ChemDraw EMF；结构本体需在 ChemDraw 修改。实验谱线输出 PNG/SVG/PDF，PPT 预览来自实际 PowerPoint 渲染。最终已确认导出会检查所有环境的确认状态。

## 测试和数据

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

真实案例测试需要本机生成的任务，仓库未附原始实验文件时会跳过。`examples/run_op_case.py` 用于自行提供 OP 示例目录；它不提供字母到峰的答案。

本仓库仅包含程序、技能、依赖和格式示例；原始核磁/结构、科研参考 PPT、生成图稿、用户人工分组配置以及虚拟环境留在本地。技能中提到的首例分组配置属于本地参考；新机器须自行提供实际分组文件。不要将某一案例的字母到峰对应推广成其他分子的默认表。
