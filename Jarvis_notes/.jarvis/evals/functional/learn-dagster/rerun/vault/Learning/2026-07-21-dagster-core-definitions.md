---
id: "learning-dagster-concepts"
title: "Dagster - Core Definitions"
type: "concept_note"
status: "draft"
created: "2026-07-21T16:43:06Z"
updated: "2026-07-21T16:43:07Z"
project_id: "functional_eval_learning"
source: "daemon"
tags: ["learning", "dagster", "definitions"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 0.7
valid_from: "2026-07-21T16:43:06Z"
review_after: ""
source_version: 1
content_hash: "b0987229cc53d2177c7a9aac0f3379da15e1d065b3abcc52864ecd81ac5dc386"
supersedes: []
contradicts: []
depends_on: ["learning-dagster-sources"]
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: ["learning-dagster-map"]
deleted: false
deleted_at: ""
fallback_reason: "preferred_local_model_failed"
learning_state: "concepts_created"
model_name: "qwen/qwen3-4b-2507"
model_provider: "lmstudio"
retrieved_at: "2026-07-21T16:35:12Z"
source_count: 10
topic: "Dagster"
workflow_id: "learn_topic_memory"
---

# Dagster - Core Definitions

## Definitions

- **ResourceDefinition:** A ResourceDefinition is a way to make external resources (like database or API connections) available to Dagster entities (like assets, schedules, or sensors) during job execution and to clean up after execution resolves [1].
- **Job:** A job is a unit of execution in Dagster that runs a set of assets or operations, and can be launched manually or automatically via schedules or sensors [2][5].
- **Asset:** An asset represents a data output in a Dagster pipeline, which can be materialized and used by other assets or jobs [5].
- **Partitioning:** Partitioning is a technique in Dagster for managing large datasets by dividing data into segments (e.g., time-based or static partitions), enabling incremental processing and improved pipeline performance [3].
- **Schedule:** A schedule is a configuration that defines when and how often a job should be executed, using intervals such as hourly, daily, or cron expressions [4].
- **Asset Sensor:** An asset sensor monitors asset materializations and triggers downstream actions (e.g., launching a job or sending a notification) based on events, enabling cross-job and cross-location dependencies [6].
- **Run:** A run is a single execution of a job in Dagster, which can be launched and viewed in the Dagster UI [2].

## Distinctions

- Schedules trigger jobs at fixed intervals (e.g., hourly, daily) based on time-based cron expressions [4].
- Asset sensors trigger jobs based on events (e.g., asset materialization) rather than time, enabling event-driven execution [6].
- Time-based partitioning divides data by time intervals (e.g., daily partitions), while static partitioning divides data into fixed, predefined segments [3].
- Asset jobs target a selection of assets and can be launched manually or via schedules/sensors [5].
- ResourceDefinition provides access to external systems during execution and ensures cleanup after runs [1].

## Examples

- Automating data pipeline execution using schedules and sensors to ensure consistent and reliable data production [2][4][7].
- Implementing time-based or static partitioning to enable incremental processing and improve performance on large datasets [3].
- Using asset sensors to monitor data materialization events and trigger downstream jobs or notifications [6].
- Leveraging asset jobs to target specific assets and streamline data processing workflows [5].
- Managing external dependencies (e.g., databases, APIs) via ResourceDefinition during job execution and cleanup [1].

## Sources

1. Concepts - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/getting-started/concepts

2. Jobs - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/build/jobs

3. Partitioning assets - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/build/partitions-and-backfills/partitioning-assets

4. Schedules - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/automate/schedules

5. Asset jobs - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/build/jobs/asset-jobs

6. Asset sensors - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/automate/asset-sensors

7. Schedules and sensors - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/api/dagster/schedules-sensors

8. Constructing schedules from partitioned assets and jobs - Dagster (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/automate/schedules/constructing-schedules-for-partitioned-assets-and-jobs

9. Overview | Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/

10. Sensors - Dagster Docs (docs.dagster.io), retrieved: 2026-07-21T16:35:12Z, backend: ddg_html
   https://docs.dagster.io/guides/automate/sensors
