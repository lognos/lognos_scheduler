# Uploader Expected Payload Contract

This document is addressed to the agent or team that implemented the schedule uploader in another application.

It defines the expected database payload for uploads into the existing `lognos_schedule` schema, according to the uploader implemented in this repository.

This is a general contract for uploading any schedule version.

A recent upload, `BIO4-24101_260306`, is used only as an example of how deviations from this contract show up in the database and later in the UI.

---

## 1. Purpose

The uploader must work for any valid Microsoft Project XML schedule version and write data in a shape that is compatible with:

- schedule analysis,
- semantic search,
- critical path tools,
- Gantt visualization,
- baseline visualization.

The required outcome is not just that rows exist in the database. The rows must contain the fields and relationships the rest of the system expects.

---

## 2. Upload contract summary

For every uploaded schedule version, the uploader is expected to write to these tables in this order:

1. `schedule_versions`
2. `project_constraints`
3. `project_calendars`
4. `schedule_activities`
5. `schedule_links`

The upload is successful only if all five layers are populated consistently.

---

## 3. Required database behavior for any uploaded version

## 3.1 `schedule_versions`

### Required behavior

Insert exactly one row representing the uploaded schedule version.

### Required fields

- `project_name`
- `version_name`
- `version_id`
- `xml_filename`
- `description`
- `is_current`
- `is_baseline`

### Version identity rules

Canonical forms:

- current version: `{PROJECT_NAME}_{YYMMDD}`
- baseline version: `{PROJECT_NAME}_{YYMMDD}_BL`

Examples:

- `BIO4-24101_260306`
- `BIO4-24101_260306_BL`

### Expected derivation rules

`project_name` should be derived using this priority:

1. filename pattern
2. XML project name
3. filename stem

`version_name` should typically be:

- `vYYMMDD` for current versions
- `Baseline vYYMMDD` for baseline files

`is_baseline` should be true only for baseline uploads.

`is_current` should be true for the latest uploaded current schedule version for a project, and prior current rows for the same project should be reset to false.

---

## 3.2 `project_constraints`

### Required behavior

Insert exactly one row for the uploaded version containing project-level schedule metadata.

### Required fields

- `project_start_date`
- `project_finish_date`
- `status_date`
- `schedule_from_start`
- `version_id`

### Source

These values come from project-level XML fields, not from activities.

---

## 3.3 `project_calendars`

### Required behavior

Insert the selected base project calendar for the uploaded version.

### Required fields

- `calendar_name`
- `is_base_calendar`
- `working_days_per_week`
- `working_hours_per_day`
- `version_id`

### Required linkage behavior

The uploader must retain the inserted `project_calendars.id` and write it into `schedule_activities.calendar_id` for activities in the uploaded version.

### Reference uploader behavior in this repo

The current uploader in this repository extracts one base calendar for the upload and uses that inserted row as the activity calendar reference.

If another uploader chooses to preserve additional calendars, it must still ensure that the activity rows used by the UI and downstream logic have a resolved calendar association compatible with the expected processing model.

---

## 3.4 `schedule_activities`

### Required behavior

Insert one row per XML task, excluding the project summary task where `UID = 0`.

### Required fields

Each uploaded activity row is expected to include:

- `ms_uid`
- `name`
- `name_verbose`
- `wbs`
- `start`
- `finish`
- `duration_d`
- `percent_complete`
- `cost`
- `is_milestone`
- `is_summary`
- `notes`
- `embedding`
- `version_id`
- `calendar_id`
- `baseline_start`
- `baseline_finish`
- `baseline_duration_d`
- `total_float_d`
- `owner`
- `cost_item_id`
- `constraint_type`
- `constraint_date`
- `actual_start`
- `actual_finish`
- `deadline_date`

### Duration contract

`duration_d` must be populated from the XML task duration and converted into working days using the uploaded project calendar.

Expected behavior:

- most non-milestone tasks should have `duration_d > 0`
- real milestones may have `duration_d = 0`
- summary tasks may also have non-zero duration

A version where nearly all tasks have `duration_d = 0` is not compatible with the expected visualization behavior.

### Baseline contract

The uploader must populate baseline fields whenever baseline data is available in the XML.

Expected logic:

1. If the task contains baseline data in `<Baseline Number='0'>`, populate:
   - `baseline_start`
   - `baseline_finish`
   - `baseline_duration_d`
2. If the uploaded file itself is a baseline file and explicit baseline task data is not present, baseline handling must still be coherent with the rest of the system. In this repository, the uploader mirrors current start and finish into baseline fields for baseline uploads.

Baseline visualization in the UI depends on these values being present in a usable form.

### Embedding contract

Each activity row must receive an embedding built from hierarchical task context.

Expected behavior in this repository:

- model: `models/gemini-embedding-001`
- dimensions: `1536`
- task type: `semantic_similarity`

The hierarchical context used for embedding includes:

- WBS ancestry
- task name
- notes
- WBS code

### Naming contract

`name_verbose` must not simply duplicate `name`. It should include the hierarchical task path derived from WBS structure so that search and UI display have a stable verbose activity label.

---

## 3.5 `schedule_links`

### Required behavior

Insert one row per valid predecessor relationship for the uploaded version.

### Required fields

- `pred_id`
- `succ_id`
- `rel_type`
- `lag_d`
- `version_id`

### Required methodology

1. Extract predecessor-successor links from XML using MS Project task UIDs.
2. Insert activities first.
3. Resolve database activity IDs for the uploaded version.
4. Insert links only after both endpoints are successfully resolved.

---

## 4. Conversion and parsing rules the uploader must respect

## 4.1 File validation

The uploader must accept only valid Microsoft Project XML files with the expected namespace.

### Required namespace

- `http://schemas.microsoft.com/project`

### Required minimal structure

- task collection exists
- at least one valid task exists besides the project summary task

---

## 4.2 Duration parsing

The uploader must parse MS Project duration values and convert them into working days using the effective project calendar.

In this repository, duration conversion is calendar-aware.

That means the uploader must not leave `duration_d` as zero simply because the raw XML duration was not parsed correctly.

---

## 4.3 Slack and lag parsing

The uploader must parse:

- task slack into `total_float_d`
- relationship lag into `lag_d`

Where raw values are encoded in MS Project time units, they must be converted consistently using calendar hours per day.

---

## 4.4 Baseline parsing

The uploader must inspect task baseline data and write baseline fields when present.

If baseline values are ignored during upload, the Gantt cannot offer reliable baseline display even if the source XML contains baseline information.

---

## 4.5 Custom fields

The uploader in this repository maps specific extended attributes into:

- `owner`
- `cost_item_id`

If the other uploader intends to remain compatible with this app’s behavior, those mappings must also be preserved.

---

## 5. Success criteria for any uploaded version

For any uploaded current schedule version, the minimum expected result is:

### schedule_versions

- exactly one canonical version row exists

### project_constraints

- exactly one row exists for the version

### project_calendars

- the uploaded version has a usable project calendar record

### schedule_activities

- one row per valid task except UID `0`
- non-zero durations for most non-milestones
- valid `calendar_id` linkage
- baseline fields populated when baseline data exists in the XML
- embeddings populated

### schedule_links

- predecessor-successor rows are inserted with resolved activity IDs

If these conditions are not met, the upload is only partially correct and downstream UI behavior can fail even though the version appears to exist.

---

## 6. Example of failure symptoms

The schedule version `BIO4-24101_260306` is an example of what happens when the uploader does not satisfy this contract.

### Observed stored symptoms

- all activity durations were stored as zero
- baseline dates were not populated
- all activity `calendar_id` values were null
- multiple project calendar rows were inserted instead of the single resolved calendar behavior used by this repo’s uploader

### Resulting UI symptoms

- activities can render as milestones because zero-duration bars are commonly treated as milestones
- baseline options do not appear because baseline dates are absent

This version is an example, not the scope of the contract.

The contract applies to every upload, regardless of project or version date.

---

## 7. What another uploader must guarantee

Any uploader targeting this schema must guarantee the following for every uploaded version:

1. generate a canonical `version_id`
2. write one coherent version row
3. write one coherent project constraint row
4. write a usable project calendar record and preserve calendar linkage into activities
5. write task rows with real durations and baseline values where applicable
6. generate embeddings in the expected format
7. resolve and insert predecessor links after activities exist
8. preserve consistency across all tables through the same `version_id`

---

## 8. Practical validation checklist for any future upload

After uploading any version, validate all of the following:

1. `schedule_versions.version_id` matches the canonical naming convention
2. `project_constraints.version_id` exists for that version
3. `project_calendars.version_id` exists for that version
4. `schedule_activities.version_id` rows exist and most non-milestones have `duration_d > 0`
5. `schedule_activities.calendar_id` is populated consistently
6. `baseline_start` and `baseline_finish` are populated when the source XML contains baseline data
7. `schedule_links.version_id` rows exist and counts are plausible for the task network
8. embeddings are present for activity rows used in semantic search

---

## 9. Action requested from the uploader agent

Please update the uploader so that it conforms to this contract for any schedule version, not only for the example version used in this analysis.

In particular, verify that your uploader:

1. parses task durations into `duration_d` correctly
2. extracts and writes baseline task fields correctly
3. assigns a resolved `calendar_id` to uploaded activities
4. preserves the canonical version naming and `version_id` pattern
5. writes data in the same relational shape expected by the rest of the system

That is the payload contract the uploader in this repository is designed to satisfy.