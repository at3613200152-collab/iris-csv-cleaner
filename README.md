# Iris 公开数据清洗小项目

这是一个面向入门学习的命令行 CSV 清洗程序，不是分类模型，也没有训练或准确率指标。

目标对应题目截图：处理编码、缺失、重复和非法值；提供小型测试、输入输出样例、失败退出码和说明文档。

只使用 Python 标准库。需要 Python 3.10 或更新版本，不需要安装 pandas、PyTorch 或其他包。

## 本次实际运行结果（2026-11-19）

- 本机 Python 3.12.14；Windows PowerShell 一键脚本已实际运行成功。
- 37 项自动测试全部通过，无跳过。
- 官方文件：150 条有效观测全部保留，另隔离末尾 1 条空行；重复只报告，不删除。
- 人工样例：15 条输入，保留 4 条，隔离 10 条非法/缺失等记录及 1 条重复记录。
- UTF-8 与 GB18030 两个版本得到完全相同的预期输出，原始公开文件哈希未改变。
- 查看[本次生成的演示结果](output/demo_20261119_084224_971162/演示结果.md)。这是真实运行记录，不是对隐藏评分用例的保证。

## 先看什么

1. `examples/dirty.csv`：人工加入异常的输入，UTF-8/BOM 编码。
2. `examples/expected_clean.csv`：启用去重时，独立列出的预期四条输出。
3. `output/`：实际演示结果；每次运行建立新的 `demo_时间戳` 子目录，里面有 `演示结果.md`。
4. `clean.py` 中的 `normalize_row` 和 `clean_rows`：先学这两个函数，其余命令行和文件部分以后再学。

以上是项目内相对路径。运行下面命令前，先在终端进入本项目文件夹。

## 当前 Windows 电脑一键运行

在本文件夹的 PowerShell 终端运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\运行演示.ps1
```

只对本次 PowerShell 进程放行本地脚本，不修改系统永久执行策略。脚本优先使用这台电脑已有的 Codex Python 运行时，再尝试 `py -3` 或 `python`。启动器本身用 ASCII 提示，避免 Windows PowerShell 5.1 误读 UTF-8 脚本；Python 输出与本文说明使用中文。

它先运行自动测试；通过后再演示原始数据、UTF-8 人工异常样例、GB18030 人工异常样例。不会联网，不覆盖以前的演示输出。

只测试时在命令末尾加 `-TestOnly`。

## 普通 Python 环境运行

```powershell
python -m unittest discover -s tests -v
python run_demo.py
```

正常的项目包已经带有公开数据和样例，不需要下载即可完成以上两步。

单独清洗带表头的样例：

```powershell
python clean.py --input examples/dirty.csv --output output/manual_clean.csv --dedup
```

处理 GB18030 编码：

```powershell
python clean.py --input examples/dirty_gb18030.csv --encoding gb18030 --output output/manual_gbk.csv --dedup
```

处理官方无表头文件，不删除相同测量记录：

```powershell
python clean.py --input data/raw/bezdekIris.data --no-header --output output/manual_official.csv
```

默认拒绝覆盖已有的三个输出。只有确需覆盖时才添加 `--overwrite`，即便指定该参数也不能覆盖当前输入。

## 公开来源与人工样例的区别

- 数据集：[UCI Iris](https://archive.ics.uci.edu/dataset/53/iris)。
- 选择官方文件 `bezdekIris.data`：[原始下载地址](https://archive.ics.uci.edu/ml/machine-learning-databases/iris/bezdekIris.data)。逗号分隔、无表头，含 150 条有效观测；当前下载快照末尾另外有一条空行。
- 引用：Fisher, R. (1936). Iris [Dataset]. UCI Machine Learning Repository. [DOI: 10.24432/C56C76](https://doi.org/10.24432/C56C76)。
- 数据许可：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。再分发时保留来源与修改说明。
- 原始下载字节保存在 `data/raw/bezdekIris.data`，未修改；来源、下载时间和 SHA-256 在旁边的 `provenance.json`。
- UCI 原始观测没有缺失字段。末尾空行会被单独隔离，不把它称为“观测中的字段缺失”。
- `examples/` 的缺失、非法值等异常是为了测试人工注入的，不能当成 UCI 原始数据质量调查结果。`fixture_manifest.json` 逐条说明源记录与修改方式。
- 两种编码样例都包含真正的中文，避免只用英文数字时“两个编码都能读”的假象。
- UCI 页面说明经典文件与论文之间的数值差异。本项目明确记录所用版本，不根据固定行号偷偷修补，也不混用其他 Iris 版本。

日常使用不需要联网。如需重新获取原始文件：

```powershell
python download_data.py
```

原始数据或来源记录已存在时会拒绝覆盖。只有明确要重下，才加 `--refresh`。重建人工样例用 `python prepare_examples.py --overwrite`，不是正常演示的必需步骤。哈希不一致时先核对，不自动重下覆盖。

## 输入格式与规则（版本 1.0）

固定五个字段为：

```csv
sepal_length_cm,sepal_width_cm,petal_length_cm,petal_width_cm,species
```

默认要求表头；允许表头改变顺序，但不能缺列、多列或重名。`--no-header` 按上述顺序读取。它是有明确 Iris 字段约束的程序，不是任意表格通用清洗器。

| 项目 | 明确规则 |
| --- | --- |
| 编码 | 默认 `utf-8-sig`，兼容 UTF-8 与 UTF-8/BOM。其他编码通过 `--encoding` 指定；不自动猜测，不忽略非法字节。 |
| 空白 | 字段删除首尾空白，不删除有效文本内部字符。 |
| 缺失 | 空字符串、`NA`、`N/A`、`null`、`None`、`?`，大小写不敏感；任何必填列缺失时隔离整行，不做均值填补。 |
| 数字 | 四个测量列必须是有限、非负浮点数；拒绝文字、NaN、无穷和负数。0 不是缺失。本版不设按数据最大最小值猜出的阈值，不声称完成生物学异常鉴定。 |
| 品种 | 只接受 `Iris-setosa`、`Iris-versicolor`、`Iris-virginica`；忽略大小写并输出标准拼写。 |
| 结构 | 数据行列数错误时隔离；CSV 引号损坏导致无法可靠解析时停止整个文件。 |
| 重复 | 规范化后五列全部相同才判重。默认只统计，`--dedup` 才保留第一条、隔离后续重复。 |
| 空行 | 单独计为异常，原因 `empty_row`，不静默丢弃。 |

相同测量值可能来自不同个体，不能断言是采集错误。因此默认不删原始重复测量，人工演示明确启用去重；品种不同不视为重复。

第一版用“隔离缺失行”减少实现负担。之前学过的均值填补可以后续独立添加，不能把缺失当成 0。

## 输出与退出码

假设指定 `--output output/manual_clean.csv`，默认生成：

- `manual_clean.csv`：清洗结果，带固定表头，UTF-8/BOM。
- `manual_clean_rejected.csv`：异常记录及原因，UTF-8/BOM。`source_record` 从第一条数据记录计数，不含表头，不是物理行号。每条记录只报告按检查顺序发现的第一个问题。`raw_row` 为输入字段数组的 JSON 表示。
- `manual_clean_report.json`：输入哈希、编码、Python 版本、规则版本、时间、行数与原因统计，UTF-8。

可用 `--rejects`、`--report` 指定后两者位置。输入与三个输出路径不能相同，也不能把某个输出文件当成另一个输出的目录。

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功生成结果，至少有一条有效记录。隔离部分坏行不等于整个文件失败。 |
| 1 | 文件、编码、CSV、表头等处理失败，或所有记录都不合法。全部非法时仍保存空结果表、异常表和 `no_valid_records` 报告，不能把零行结果误称成功。 |
| 2 | 参数错误，如缺少必填参数、不支持的编码名、输入输出路径冲突等。 |

空文件与只有表头的文件会失败，不生成输出。解码和解析在写出之前完成；不会在坏字节处截断后宣称成功。若磁盘写入中途失败仍可能留下部分输出，返回 1；本入门版没有跨三个文件的事务机制，使用结果前检查退出码。

统计恒等式：`输入记录数 = 输出记录数 + 隔离记录数`。重复计数是首条之后的重复次数；只有启用去重时计入删除/隔离。

PowerShell 在运行后查看 `$LASTEXITCODE`；CMD 查看 `%ERRORLEVEL%`。

## 验证方式

```powershell
python -m unittest discover -s tests -v
```

覆盖正常值与 0、缺失标记、空白、数字转换、NaN/Inf、负数、类别、空行、列数、重复开关、表头换序/缺列/重名、无表头不丢首行、中文与错误编码、CSV 引号、文件不存在、全部非法、覆盖保护和幂等性。两个编码版本都与独立预期输出比对。

测试不联网，不改原始文件，临时记录由测试框架放入系统临时目录并清理。可更换输入行数、顺序与内容；若字段结构不同，需要另定规则。

## 初学者阅读顺序

1. `normalize_row`：清理首尾空白 → 检查缺失 → `float` → 数值检查 → `append` → `return`。
2. `clean_rows`：`for` 逐行处理，`if/else` 区分保留和隔离，列表保存结果。
3. 新知识先补 `try/except`（处理转换失败）和 `set`（记住已见过的记录）。
4. 最后学 CSV 文件与 `argparse`，不用一次背完整程序。

可以修改人工样例做实验；如果结果变化，独立预期比对测试就会失败，这是合理反馈。程序不会偷偷重置你修改的样例。备份改动后，才显式重建样例。

## 提交边界

- 可运行的入门版，不保证满足尚未提供的评分细则。老师若要求缺失必须填补或其他字段，以正式要求为准调整。
- 处理能整体读入内存的小型 CSV，不是超大文件流式工具。
- 报告保留运行环境与数据哈希；本次没有初始化上级 Git 仓库、创建或推送提交。要版本管理时，只在本项目目录另建仓库，并记录实际 commit。
- 清洗记录数不是模型训练或分类评测成绩。
#   i r i s - c s v - c l e a n e r  
 