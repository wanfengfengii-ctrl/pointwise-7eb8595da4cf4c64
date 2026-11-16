# 样条分析归档升级候选的公开契约

## 现有工程及入口

这是完整可运行的旧系统，不是已经完成的迁移实现。Python 标准库与 SQLite 是全部依赖，vendor/spline1.py 和 vendor/poly2.py 是随题离线提供的两个内部 SDK 的完整源码，不模拟某个未提供的商业 SDK。没有曲线拟合、性能优化、并发写入或在线迁移要求。

archive.Store(db) 和 analysis.Analysis(db) 共用调用方打开的 sqlite3.Connection，调用方负责关闭连接。samples.open_sample(path=":memory:") 构造完整旧库并返回连接；构造文件库用 python3 samples.py sample.db，要求目标路径尚无这些表。旧 Schema 原文在 archive.SCHEMA，可通过 sqlite_master 查询。所有 ID 和任务名为非空字符串。输入协方差保证对称半正定；不要求新增半正定性判定器。

Store.replace(id,payload) 原子替换曲线，Store.value(id,x) 返回 Fraction。Analysis.save(name,id,lo,hi) 保存或替换具名分析，Analysis.run(name) 返回二元组(Fraction均值,Fraction方差)。任务引用曲线 ID，不冻结曲线内容，曲线替换后任务分析当前曲线。缺失 ID/任务抛 KeyError；越界点、反向或越界积分区间抛 ValueError。lo=hi 合法，返回(0,0)。不存在曲线删除入口。

旧载荷是 JSON 对象，只有 knots、mean、cov 三项；各数序列化为 Fraction 可解析字符串，例如 "2" 或 "-3/7"。knots 为 n+4 个非降结点，mean 为 n 个系数均值，cov 为 n×n 联合协方差；4≤n≤8。次数固定三次，两端结点恰重复四次，内部结点重数1至4。定义域为[knots[3],knots[n]]。内部结点取右段，定义域右端取左极限；重复结点和零长度段不得改变结果。输入来自合法业务数据，维度、域和对称性错误沿现有 SDK 拒绝，不扩大校验范围。

样本 offset 的完整载荷为 {"knots":["0","0","0","0","1","2","2","2","2"],"mean":["3","3","3","3","3"],"cov":[["1","1","1","1","1"],["1","1","1","1","1"],["1","1","1","1","1"],["1","1","1","1","1"],["1","1","1","1","1"]]}。
其 whole 任务为("offset","0","2")，返回(6,4)；empty 为("offset","1","1")，返回(0,0)。
jump 使用结点[0,0,0,0,1,1,1,1,2,2,2,2]、均值[1,1,1,1,7,7,7,7]和8阶单位协方差，value(jump,1)=7，jump-total 在[0,2]返回(8,1/2)。samples.py 还完整构造内部重数1至4、有理均值、含负相关的奇异协方差数据；没有外部数据文件依赖。

## 本次迁移及目标接口

新增 migration.upgrade(db,before_commit=lambda: None) -> bool，使用已提供的 archive.atomic_upgrade 事务设施：首次成功返回 True，已经升级返回 False。维护窗口单工作者、无活动调用方事务；只处理本连接完整旧库，不需要分批复制、断点恢复或多个进程竞争。SDK1 不提供基底转换；SDK2 不提供样条转换、积分分析或联合不确定度运输。

真实生成 curves2、jobs2，原 curves1、jobs1 保持逐字审计原文，不再用于升级后的业务读写。jobs2 的名称、曲线 ID、端点与旧任务一致；meta 唯一行的 version 从1变2。曲线表示、分析绑定及版本共同原子切换；失败保全旧库，重复升级无副作用。before_commit 在目标写入后、版本提交前调用，异常原样传播；事务设施已正确实现回滚，不把重做这一设施作为交付内容。

SDK2 Schema 为 poly2.SCHEMA。poly2.initialize(db) 创建目标表；replace(db,id,payload) 写入或覆盖，read(db,id) 返回解码后的目标载荷，value(payload,x) 返回均值曲线点值。SDK2 写入参与调用方事务，不自行提交。原生替换沿用已经存在的曲线 ID，并保证旧任务端点仍在新定义域内。

目标载荷 edges 为严格递增的段边界；每个相邻边界之间一个非空段。mean 按段顺序扁平排列，每段四项，分别是以左边界为原点的0、1、2、3次幂系数。不得在目标载荷保存旧 knots 或旧 B 样条系数来代替实际转换。

uncertainty 允许以下两种完整格式，必须支持 SDK2 原生写入的两种表示：
* {"kind":"cov","matrix":Q}：Q 是全部目标多项式系数的完整联合协方差。
* {"kind":"factor","loadings":A,"latent_cov":C}：目标随机系数的中心化部分为 A z，z 的联合协方差为 C；A 的行数等于目标系数数目，C 为至少1阶的对称半正定方阵，可奇异。

目标所有数仍精确保存为有理数字符串；poly2.read 返回 Fraction。迁移自行选择上述一种表示，原生替换可使用另一种，不新增接口。迁移须保留跨段相关性，跨多个区间的积分方差不能按各段方差直接相加。SDK2 原生替换示例：edges=[0,1,2]，mean=[9,0,0,0,9,0,0,0]，loadings=[[2],[0],[0],[0],[2],[0],[0],[0]]，latent_cov=[[1]]；uncertainty.kind 为 factor。whole 此后返回(18,16)。示例数字写入时可先经 rational.dumps 转为有理数字符串。

保留 Store.replace/value 和 Analysis.save/run 的调用方式、异常及 Fraction 结果。切换后查询只用SDK2及目标表，既有Analysis对象须立即看见SDK2原生替换的曲线及其联合不确定度。不得缓存旧载荷、沿旧 SDK 求值或从审计表重建目标业务结果；检查时会禁止调用 spline1.load/basis/weights/value/integral。Store.replace 接收原旧载荷后也须在适配层转为目标表示，允许调用不涉及 SDK1 的自有转换逻辑。每次分析运行采用同一事务快照内的任务绑定、曲线均值和联合不确定度。

## 运行、核验与交付

python3 checks.py baseline 核对旧业务、目标 SDK 原生点值及现成事务设施；成功打印 BASELINE_OK，展示 whole=(6,4)、jump-total=(8,1/2) 和回滚保全。
python3 checks.py demo 展示真实旧任务及结点跳变结果。基础回归原断言须保留；交付时使其同时兼容升级前后公开旧接口。

.pointwise-runtime.json 是供调用方读取的运行清单，version 固定为1，kind 为 cli；setup 是零个或多个命令的 argv 数组列表，verify 与 demo 分别是一条命令的 argv 数组，不使用 shell 字符串。当前清单运行完整旧业务。交付时更新 verify/demo，使核验和演示实际经过旧库构造、升级、既有对象查询及 SDK2 原生替换。

交付兼容实现、独立语义对照与简短的基底转换及不确定度表示说明。独立对照以旧 SDK 的点值和积分权重核对迁移结果，覆盖各重数、结点两侧和右端、跨段及空区间、正负相关和奇异协方差；核对目标持久载荷与旧审计原文。禁用 SDK1 后重跑已保存分析并做上述原生替换，确认目标表独立供读；注入提交前异常，核对旧库完整及无半迁移结果，再重试并重复升级。该核验不要求操作系统杀进程、内存基准或额外的输出报告 Schema。

## 冻结的原生兼容样例

native_cases.cases() 返回四个(name,payload,expected)三元组，每次调用重新构造独立载荷；expected 只列公开分析预期，不是分析实现。区间 left=[0,1]、right=[1,2]、whole=[0,2]、empty=[1,1]。shared-cov 与 shared-factor 表达同一曲线：两个常数段共享随机偏移，left、right 均为(9,4)，whole=(18,16)。opposed-cov 与 opposed-factor 表达另一条均值相同的曲线：两段随机偏移符号相反，left、right 仍为(9,4)，whole=(18,0)。四者 empty 均为(0,0)，各合法点的均值均为9。两组均为奇异半正定不确定度。

这些载荷可直接通过 poly2.replace(db,"offset",payload) 原生替换；应在升级后使用预先创建的 Analysis 对象核对上述区间。迁移前可用 Analysis.save 保存相应任务。python3 native_cases.py 只核对样例自身、SDK2 解码和旧 offset 对照，不实现迁移或目标积分；python3 checks.py baseline 同时执行该样例核对。交付核验仍须实际调用升级后的 Analysis.run，不能把样例自身检查当作迁移验收。
