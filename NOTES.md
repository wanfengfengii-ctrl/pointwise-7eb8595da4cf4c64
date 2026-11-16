# 基底转换与不确定度表示

## 曲线表示

旧库每条曲线是 n+4 个结点的夹持三次 B 样条，定义域 [knots[3], knots[n]]。
目标载荷只存段边界 `edges` 与每段局部幂系数：

* `edges` 是 `knots[3:n+1]` 中互不相同的值，因此每个相邻边界之间都是非空段；
  旧库的零长度段（重复结点）在目标侧自然消失，结点跳变体现为相邻段不同的
  多项式，右端取左极限，与旧语义一致。
* 每段 4 个系数是 `mean[4i:4i+4]`，以该段左边界为原点的 0..3 次幂系数。

## 转换

每段在开 Newton-Cotes 四点 `{1/5,2/5,3/5,4/5}` 处采样旧样条（该四点也是旧
`weights` 的积分节点）。段内旧样条是三次多项式，故四点是可逆插值；用范德蒙
逆矩阵把节点值还原成幂系数。对每段的线性映射记为行向量 `R_i`，则

* 目标均值 `mean_i = R_i · m`；
* 目标协方差 `Q_ij = R_i C R_j^T`。

`Q` 保存全部目标系数的联合协方差，所以跨段协方差不会丢失，多段区间的积分方差
是 `w^T Q w`，不等于各段方差之和。迁移选择 `kind:"cov"` 的完整表示；时间与
空间都可接受（q ≤ 32）。

## 不确定度的两种原生形式

* `cov`：`matrix` 为 q×q 联合协方差，直接 `w^T Q w`。
* `factor`：`loadings` A 为 q×k，`latent_cov` C 为 k×k 半正定（可奇异）。
  积分方差为 `(A^T w)^T C (A^T w)`。分析层对两种形式走同一权重向量，不区分
  来源，也不缓存旧载荷。

## 分析边界

`Analysis.run` 用一条 SQL 同时取版本、任务绑定和曲线载荷，保证均值和方差来自
同一快照；`run` 每次重新读取 curves2/jobs2，因此同 ID 原生替换后立即生效。
`Store.replace` 在 v1 下写旧表，在 v2 下把旧载荷经 `convert.py` 转成目标表示后
写入 curves2；二者都不改变公开接口、异常或 Fraction 结果。

## 文件

* `convert.py`：旧载荷校验、独立 B 样条求值、转换、目标侧积分与方差。
* `migration.py`：`upgrade(db, before_commit)`，复用 `archive.atomic_upgrade`。
* `archive.py` / `analysis.py`：双代兼容的 Store/Analysis。
* `compare.py`：以旧 SDK 为独立基准的语义对照。
* `checks.py`：`baseline`（保留原断言）、`verify`（真实升级核验）、`demo`。
