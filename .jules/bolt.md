# Bolt's Journal - Critical Learnings

## 2025-05-18 - Single-Pass Metric Grouping in Analysis
**Learning:** In comparative grade analysis, grouping paired rows separately per metadata attribute (domain, family/workflow, complexity, split) iterates over all matched rows multiple times and recreates tuple pairs repeatedly. Building grouping maps in a single iteration reduces overall execution time by ~25%.
**Action:** Aggregate grouping tuples in a single loop over rows when building multi-faceted benchmark comparison summaries.
