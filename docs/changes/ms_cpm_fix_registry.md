# MS Project CPM Fix Change Registry

### [DONE] Change ID: 1

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `load_from_ms()`
**Change Type**: MODIFIED
**Phase**: 1
**Root Cause**: RC-1

**Description**: Added project start resolution logic using project constraints first, then fallback to minimum non-summary activity start.

**Lines Before**: ~396-512
**Lines After**: ~396-629

**Dependencies**: None
**Dependents**: 3, 14

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification in Gantt flow
- [ ] Date comparison: Pending runtime verification

**Notes**: Keeps fallback logic to avoid regressions when constraints are absent.

### [DONE] Change ID: 2

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `ScheduleWorkspace`
**Change Type**: MODIFIED
**Phase**: 1
**Root Cause**: RC-1

**Description**: Added `calendar_exceptions` field to persist MS working-time exceptions in workspace state.

**Lines Before**: ~22-66
**Lines After**: ~22-67

**Dependencies**: None
**Dependents**: 10, 11, 12, 14

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification in Gantt flow
- [ ] Date comparison: Pending runtime verification

**Notes**: Field defaults to an empty list for compatibility with schedules that do not define relationship metadata.

### [DONE] Change ID: 3

**File**: `backend/tools/ms/workspace.py`
**Function/Class/Model**: `load_schedule_ms()`
**Change Type**: MODIFIED
**Phase**: 1
**Root Cause**: RC-1

**Description**: Loaded `project_constraints` and `constraint_types` via repository and passed them into `load_from_ms()`.

**Lines Before**: ~12-96
**Lines After**: ~12-102

**Dependencies**: 1
**Dependents**: 15

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification in MS load flow
- [ ] Date comparison: Pending runtime verification

**Notes**: Reused existing repository methods, no repository schema/API changes needed.

### [DONE] Change ID: 4

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `load_from_ms()`
**Change Type**: MODIFIED
**Phase**: 2
**Root Cause**: N/A

**Description**: Preserved source MS dates in `original_start` / `original_finish` and normalized date columns for later comparison.

**Lines Before**: ~430-475
**Lines After**: ~470-555

**Dependencies**: 1
**Dependents**: 6

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification in calculate flow
- [ ] Date comparison: Pending runtime verification

**Notes**: Falls back to target dates if original dates are absent.

### [DONE] Change ID: 5

**File**: `backend/tools/workspace/mutations.py`
**Function/Class/Model**: `calculate_gantt_ws()`
**Change Type**: MODIFIED
**Phase**: 2
**Root Cause**: N/A

**Description**: Added MS validation call after CPM calculation and logged validation summary; included match summary in tool response.

**Lines Before**: ~252-588
**Lines After**: ~252-620

**Dependencies**: 6
**Dependents**: None

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with MS project load + Gantt
- [ ] Date comparison: Pending runtime verification

**Notes**: Validation runs only when `workspace.source == "ms_loaded"`.

### [DONE] Change ID: 6

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `validate_against_ms_dates()`
**Change Type**: NEW
**Phase**: 2
**Root Cause**: N/A

**Description**: Added per-activity date comparison against stored MS dates with tolerance and discrepancy reporting.

**Lines Before**: N/A
**Lines After**: ~515-617

**Dependencies**: 4
**Dependents**: 5

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification in MS flow
- [ ] Date comparison: Implemented, runtime execution pending

**Notes**: Emits per-activity Logfire records (`MS date comparison`).

### [DONE] Change ID: 7

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `build_network()`
**Change Type**: MODIFIED
**Phase**: 3
**Root Cause**: RC-2

**Description**: Preserved actual relationship types on edges (`PR_FS/PR_SS/PR_FF/PR_SF`) instead of forcing non-FS behavior.

**Lines Before**: ~198-258
**Lines After**: ~198-258

**Dependencies**: None
**Dependents**: 8, 9

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with SS/FF/SF links
- [ ] Date comparison: Pending runtime verification

**Notes**: Normalizes missing `PR_` prefix safely.

### [DONE] Change ID: 8

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `forward_pass()`
**Change Type**: MODIFIED
**Phase**: 3
**Root Cause**: RC-2

**Description**: Implemented ES/EF derivation formulas for FS, SS, FF, and SF relationships, including lag handling.

**Lines Before**: ~289-390
**Lines After**: ~316-390

**Dependencies**: 7
**Dependents**: None

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with mixed link types
- [ ] Date comparison: Pending runtime verification

**Notes**: Constraint application remains in forward pass and now uses normalized dates.

### [DONE] Change ID: 9

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `backward_pass()`
**Change Type**: MODIFIED
**Phase**: 3
**Root Cause**: RC-2, RC-6

**Description**: Implemented LF/LS derivation formulas for FS, SS, FF, and SF relationships with lag handling.

**Lines Before**: ~392-468
**Lines After**: ~392-468

**Dependencies**: 7
**Dependents**: None

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with mixed link types + lag
- [ ] Date comparison: Pending runtime verification

**Notes**: Replaced simplified FS-only branch.

### [DONE] Change ID: 10

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `__init__()`
**Change Type**: MODIFIED
**Phase**: 4
**Root Cause**: RC-3

**Description**: Added `calendar_exceptions` constructor argument and persisted it as a set for fast date checks.

**Lines Before**: ~94-132
**Lines After**: ~94-134

**Dependencies**: 2, 13, 14
**Dependents**: 11, 12

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with exception dates
- [ ] Date comparison: Pending runtime verification

**Notes**: Optional argument keeps old call sites valid.

### [DONE] Change ID: 11

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `_days_to_work_date()`
**Change Type**: MODIFIED
**Phase**: 4
**Root Cause**: RC-3

**Description**: Updated date stepping to skip weekends and calendar exceptions; supports both forward and backward movement.

**Lines Before**: ~143-161
**Lines After**: ~164-181

**Dependencies**: 10
**Dependents**: 8, 9

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with holiday-spanning activities
- [ ] Date comparison: Pending runtime verification

**Notes**: Uses helper methods for date coercion and workday checks.

### [DONE] Change ID: 12

**File**: `backend/services/network_calculator.py`
**Function/Class/Model**: `_work_days_between()`
**Change Type**: MODIFIED
**Phase**: 4
**Root Cause**: RC-3

**Description**: Updated work-day interval calculation to exclude exception dates in addition to weekends.

**Lines Before**: ~163-176
**Lines After**: ~183-195

**Dependencies**: 10
**Dependents**: float/critical calculations

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with exception dates
- [ ] Date comparison: Pending runtime verification

**Notes**: Preserves prior behavior for projects without exceptions.

### [DONE] Change ID: 13

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `load_from_ms()`
**Change Type**: MODIFIED
**Phase**: 4
**Root Cause**: RC-3

**Description**: Loaded and normalized `calendar_exceptions` from MS calendar payload into workspace state.

**Lines Before**: ~486-512
**Lines After**: ~592-629

**Dependencies**: 2, 3
**Dependents**: 14

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification
- [ ] Date comparison: Pending runtime verification

**Notes**: Exception dates deduplicated and sorted.

### [DONE] Change ID: 14

**File**: `backend/tools/workspace/mutations.py`
**Function/Class/Model**: `calculate_gantt_ws()`
**Change Type**: MODIFIED
**Phase**: 4
**Root Cause**: RC-3

**Description**: Passed workspace `calendar_exceptions` into `NetworkCalculator` to enable holiday-aware CPM calculations.

**Lines Before**: ~255-259
**Lines After**: ~255-260

**Dependencies**: 10, 13
**Dependents**: None

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification
- [ ] Date comparison: Pending runtime verification

**Notes**: Applies to MS schedules; schedules without this metadata keep the empty-list default.

### [DONE] Change ID: 15

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `load_from_ms()`
**Change Type**: MODIFIED
**Phase**: 5
**Root Cause**: RC-4

**Description**: Added constraint type mapping from MS values/IDs to engine-compatible `CS_*` values and mapped `constraint_date`.

**Lines Before**: ~430-475
**Lines After**: ~423-535

**Dependencies**: 3
**Dependents**: 8

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending constrained-activity verification
- [ ] Date comparison: Pending runtime verification

**Notes**: Supports direct `CS_*`, integer IDs, and textual fallback labels.

### [NOT NEEDED] Change ID: 16

**File**: `backend/repositories/ms_schedule_repository.py`
**Function/Class/Model**: `(query constraint_types)`
**Change Type**: NONE
**Phase**: 5
**Root Cause**: RC-4

**Description**: No change required. Repository already exposes `get_constraint_types()` and was reused by MS workspace loader.

**Lines Before**: ~257-262
**Lines After**: unchanged

**Dependencies**: None
**Dependents**: 3, 15

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification
- [ ] Date comparison: Pending runtime verification

**Notes**: Kept existing repository API intact.

### [DONE] Change ID: 17

**File**: `backend/services/schedule_state.py`
**Function/Class/Model**: `load_from_ms()`
**Change Type**: MODIFIED
**Phase**: 6
**Root Cause**: RC-5

**Description**: Derived `status_code` from `percent_complete` and computed `remain_drtn_hr_cnt` proportionally to completion percentage.

**Lines Before**: ~455-468
**Lines After**: ~500-520

**Dependencies**: None
**Dependents**: build_network status mapping

**Validation**:
- [ ] Unit test: N/A
- [ ] Integration test: Pending runtime verification with complete/in-progress tasks
- [ ] Date comparison: Pending runtime verification

**Notes**: Uses bounded numeric conversion for robust handling of null/invalid values.
