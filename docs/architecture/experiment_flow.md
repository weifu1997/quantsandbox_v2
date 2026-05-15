# 实验流程（Phase 1）

## 异步主流程

1. 提交 `POST /api/experiments`
2. 创建 experiment 记录
3. 创建 task 记录并标记 `running`
4. 后台 runner 执行完整实验：
   - build dataset
   - factor research
   - backtest
   - report build
5. 写入 dataset metadata / report metadata
6. task 标记 `completed` 或 `failed`

## 同步核心执行函数

核心编排函数：
- `app.services.experiment_service.run_experiment`

该函数负责：
- 更新 task progress
- 构建 dataset
- 运行 factor validation
- 运行 TopN backtest
- 生成 report
- 更新最终 task 状态

## 当前限制

- 第一阶段使用单进程线程池，不是 durable queue
- 任务状态持久化，但运行过程不支持跨进程恢复
- 测试环境对后台线程完成时序不做强保证，因此完整成功链路主要由同步端到端测试覆盖
