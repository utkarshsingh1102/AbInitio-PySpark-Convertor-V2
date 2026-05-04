"""Three-stage IR optimizer pipeline + report aggregation.

Stage order is fixed:

  Stage 1 (structural): rewires the IR DAG and tags structure-level
    annotations (cache, broadcast strategy, projection pruning).

  Stage 2 (expression): rewrites individual expression strings inside
    transform/filter nodes.

  Stage 3 (write): adds runtime annotations consumed by the codegen
    (coalesce/repartition before write, storage levels, partitionBy,
    co-partitioning before sort-merge).
"""
from __future__ import annotations

from typing import Iterable, List

from ..ir.models import IRNode
from .rules import expression as E
from .rules import structural as S
from .rules import write as W
from .rules.base import OptimizationReport, OptimizerRule

# ── default rule pipeline ──────────────────────────────────────────────────

DEFAULT_STAGE_1: tuple[type[OptimizerRule], ...] = (
    S.EarlyFilterPushdown,
    S.ProjectionPruning,
    S.CollapseConsecutiveTransforms,
    S.JoinStrategyAnnotation,
    S.FanOutCacheAnnotation,
    # EliminatePassthroughNodes runs in stage 2 because it depends on
    # StripIdentityAssignments having run first. (Plan-level naming
    # called it structural; in practice we need it after Strip.)
)

DEFAULT_STAGE_2: tuple[type[OptimizerRule], ...] = (
    E.RewriteUDFsToNativeFunctions,
    E.StripIdentityAssignments,
    S.EliminatePassthroughNodes,
    E.FixDateTimeExpressions,
    E.TypeNullLiterals,
    E.NullSafeComparisonRewrite,
    E.DeduplicateCommonSubexpressions,
    # Last: convert remaining SQL strings to idiomatic native PySpark API.
    E.RewriteExprToNativeAPI,
)

DEFAULT_STAGE_3: tuple[type[OptimizerRule], ...] = (
    W.PartitionByAnnotation,
    W.RepartitionBeforeShuffleJoin,
    W.StorageLevelSelection,
    W.CoalesceBeforeWrite,
)


def optimize(
    nodes: List[IRNode],
    *,
    pipeline_id: str = "",
    extra_stage_1: Iterable[OptimizerRule] = (),
    extra_stage_2: Iterable[OptimizerRule] = (),
    extra_stage_3: Iterable[OptimizerRule] = (),
) -> tuple[List[IRNode], OptimizationReport]:
    """Run the full pipeline. Returns ``(optimized_ir, report)``."""
    report = OptimizationReport(pipeline_id=pipeline_id)
    cur = nodes

    for rule_cls in DEFAULT_STAGE_1:
        cur = rule_cls()(cur, report)
    for r in extra_stage_1:
        cur = r(cur, report)

    for rule_cls in DEFAULT_STAGE_2:
        cur = rule_cls()(cur, report)
    for r in extra_stage_2:
        cur = r(cur, report)

    for rule_cls in DEFAULT_STAGE_3:
        cur = rule_cls()(cur, report)
    for r in extra_stage_3:
        cur = r(cur, report)

    return cur, report
