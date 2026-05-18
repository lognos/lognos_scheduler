"""
NetworkX-based CPM (Critical Path Method) calculator for schedule workspaces.

This module provides schedule calculation functionality using NetworkX DiGraph
for dependency network representation and CPM algorithm implementation.

Current Scope:
- All standard relationship types (FS/SS/FF/SF)
- Simplified 8h/day, 5 days/week calendar with exception dates
- "Start On or After" (MSOA/SNET) constraint support
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional
import pandas as pd
import networkx as nx
import logfire


class RelationshipType(str, Enum):
    """Normalized relationship types used by schedule workspaces."""
    FS = "PR_FS"  # Finish-to-Start (MVP)
    SS = "PR_SS"  # Start-to-Start (post-MVP)
    FF = "PR_FF"  # Finish-to-Finish (post-MVP)
    SF = "PR_SF"  # Start-to-Finish (post-MVP)


class ConstraintType(str, Enum):
    """Normalized constraint types. MVP focuses on MSOA/SNET."""
    ASAP = "CS_ASAP"      # As Soon As Possible (default)
    MSOA = "CS_MSOA"      # Must Start On or After
    SNET = "CS_SNET"      # Start No Earlier Than (same as MSOA)
    # Future: MEOB, MSO, MEO, SNLT, FNET, FNLT


class ScheduleValidationError(Exception):
    """Raised when schedule validation fails."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Schedule validation failed: {'; '.join(errors)}")


@dataclass
class CalculatedActivity:
    """Result of CPM calculation for a single activity."""
    task_id: int
    task_code: str
    task_name: str
    wbs_id: Optional[int]
    wbs_path: Optional[str]
    duration_days: float
    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    total_float_days: float
    free_float_days: float
    is_critical: bool
    status: str  # 'not_started', 'active', 'complete'
    constraint_type: Optional[str] = None
    constraint_date: Optional[date] = None


@dataclass
class CalculationResult:
    """Complete result of CPM calculation."""
    activities: list[CalculatedActivity]
    project_start: date
    project_finish: date
    critical_path_ids: list[int]
    critical_path_length_days: float
    warnings: list[str] = field(default_factory=list)


class NetworkCalculator:
    """
    NetworkX-based CPM calculator for schedule workspaces.
    
    Responsibilities:
    - Build dependency graph from activities and relationships DataFrames
    - Perform forward and backward pass
    - Calculate float and identify critical path
    - Support Start On or After constraints (MVP)
    
    Calendar: Simplified 8 hours/day, 5 days/week (MVP)
    """
    
    # MVP: Default calendar settings
    DEFAULT_HOURS_PER_DAY = 8.0
    DEFAULT_DAYS_PER_WEEK = 5
    
    def __init__(
        self,
        activities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
        hours_per_day: float = DEFAULT_HOURS_PER_DAY,
        project_start_date: Optional[date] = None,
        calendar_exceptions: Optional[list[date]] = None,
    ):
        """
        Initialize the calculator.
        
        Args:
            activities_df: DataFrame with columns:
                - task_id (int): Unique identifier
                - task_code (str): User-visible code
                - task_name (str): Activity description
                - duration_hours (float): Duration in hours
                - wbs_id (int, optional): WBS identifier
                - wbs_path (str, optional): WBS hierarchy path
                - status_code (str): TK_NotStart, TK_Active, TK_Complete
                - constraint_type (str, optional): CS_ASAP, CS_MSOA, CS_SNET, etc.
                - constraint_date (date, optional): Constraint date if applicable
                
            relationships_df: DataFrame with columns:
                - task_id (int): Successor task ID
                - pred_task_id (int): Predecessor task ID
                - pred_type (str): PR_FS, PR_SS, PR_FF, PR_SF
                - lag_hr_cnt (float): Lag in hours (negative = lead)
                
            hours_per_day: Hours per work day (default 8.0)
            project_start_date: Project start date (default today)
        """
        self.activities_df = activities_df.copy()
        self.relationships_df = relationships_df.copy()
        self.hours_per_day = hours_per_day
        self.project_start = project_start_date or date.today()
        self.calendar_exceptions = set(calendar_exceptions or [])
        
        self.graph: Optional[nx.DiGraph] = None
        self._warnings: list[str] = []
        
    def _hours_to_days(self, hours: float) -> float:
        """Convert hours to work days. Handles NaN/None by returning 0."""
        if hours is None or (isinstance(hours, float) and pd.isna(hours)):
            return 0.0
        return hours / self.hours_per_day

    def _normalize_days(self, work_days: float) -> int:
        """Normalize work-day values to integer steps for date arithmetic."""
        if work_days is None or (isinstance(work_days, float) and pd.isna(work_days)):
            return 0
        if work_days >= 0:
            return int(work_days)
        return -int(abs(work_days))

    def _coerce_date(self, value: object) -> Optional[date]:
        """Convert incoming value to date if possible."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, date):
            return value
        parsed = pd.to_datetime(value, errors='coerce')
        if pd.isna(parsed):
            return None
        return parsed.date()

    def _is_work_day(self, value: date) -> bool:
        """Return True if date is a work day according to weekday + exceptions."""
        return value.weekday() < 5 and value not in self.calendar_exceptions
    
    def _days_to_work_date(self, start_date: date, work_days: float) -> date:
        """
        Add/subtract work days to a date, skipping weekends and exception dates.
        """
        normalized_days = self._normalize_days(work_days)
        if normalized_days == 0:
            return start_date

        step = 1 if normalized_days > 0 else -1
        result = start_date
        days_remaining = abs(normalized_days)

        while days_remaining > 0:
            result += timedelta(days=step)
            if self._is_work_day(result):
                days_remaining -= 1

        return result
    
    def _work_days_between(self, start_date: date, end_date: date) -> float:
        """Calculate work days between two dates (excluding weekends and exceptions)."""
        if end_date <= start_date:
            return 0.0
            
        work_days = 0
        current = start_date
        while current < end_date:
            current += timedelta(days=1)
            if self._is_work_day(current):
                work_days += 1
                
        return float(work_days)
    
    @logfire.instrument("network_calculator.build_network")
    def build_network(self) -> nx.DiGraph:
        """
        Build NetworkX DiGraph from activities and relationships.
        
        Nodes: Activities with attributes (duration, constraints, etc.)
        Edges: Dependencies with lag values
        
        Returns:
            NetworkX DiGraph representing the schedule network
        """
        self.graph = nx.DiGraph()
        
        # Add activity nodes
        for _, row in self.activities_df.iterrows():
            # Support both workspace duration columns.
            duration_hours = row.get('target_drtn_hr_cnt') or row.get('duration_hours') or 0
            duration_days = self._hours_to_days(duration_hours)
            
            self.graph.add_node(
                row['task_id'],
                task_code=row['task_code'],
                task_name=row['task_name'],
                duration=duration_days,
                wbs_id=row.get('wbs_id'),
                wbs_path=row.get('wbs_path', ''),
                status=self._map_status_code(row.get('status_code', 'TK_NotStart')),
                constraint_type=row.get('constraint_type'),
                constraint_date=row.get('constraint_date'),
                # CPM results (to be calculated)
                early_start=None,
                early_finish=None,
                late_start=None,
                late_finish=None,
                total_float=None,
                free_float=None,
            )
        
        # Add relationship edges
        for _, row in self.relationships_df.iterrows():
            pred_id = row['pred_task_id']
            succ_id = row['task_id']
            pred_type = row.get('pred_type', 'PR_FS')
            lag_hours = row.get('lag_hr_cnt', 0)
            lag_days = self._hours_to_days(lag_hours)

            if pred_type and not str(pred_type).startswith('PR_'):
                pred_type = f"PR_{pred_type}"
            
            # Validate nodes exist
            if pred_id not in self.graph.nodes:
                self._warnings.append(f"Predecessor {pred_id} not found for relationship to {succ_id}")
                continue
            if succ_id not in self.graph.nodes:
                self._warnings.append(f"Successor {succ_id} not found for relationship from {pred_id}")
                continue
            
            self.graph.add_edge(
                pred_id,
                succ_id,
                pred_type=pred_type,
                lag=lag_days
            )
        
        return self.graph
    
    def _map_status_code(self, status_code: str) -> str:
        """Map normalized status code to simplified status."""
        mapping = {
            'TK_NotStart': 'not_started',
            'TK_Active': 'active',
            'TK_Complete': 'complete',
        }
        return mapping.get(status_code, 'not_started')
    
    @logfire.instrument("network_calculator.validate_network")
    def validate_network(self) -> list[str]:
        """
        Validate the network for CPM calculation.
        
        Checks:
        - No cycles (would cause infinite loop)
        - All activities have durations
        - Network is connected (warning only)
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if self.graph is None:
            errors.append("Network not built. Call build_network() first.")
            return errors
        
        # Check for cycles
        try:
            cycles = list(nx.simple_cycles(self.graph))
            if cycles:
                cycle_strs = [' -> '.join(str(n) for n in c) for c in cycles[:3]]
                errors.append(f"Circular dependencies detected: {'; '.join(cycle_strs)}")
        except nx.NetworkXError as e:
            errors.append(f"Cycle detection error: {e}")
        
        # Check for activities with zero/negative duration
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get('duration', 0) < 0:
                errors.append(f"Activity {node_id} has negative duration")
        
        # Check for disconnected components (warning)
        if not nx.is_weakly_connected(self.graph) and len(self.graph.nodes) > 1:
            num_components = nx.number_weakly_connected_components(self.graph)
            self._warnings.append(
                f"Network has {num_components} disconnected components. "
                "Activities without predecessors will start at project start."
            )
        
        return errors
    
    @logfire.instrument("network_calculator.forward_pass")
    def forward_pass(self) -> None:
        """
        Calculate Early Start (ES) and Early Finish (EF) dates.
        
        Algorithm:
        1. Topologically sort activities
        2. For each activity:
           - ES = max(predecessor-derived starts, project_start)
           - EF = ES + duration
        3. Apply constraints (Start On or After)
        """
        if self.graph is None:
            raise ValueError("Network not built")
        
        # Get topological order
        try:
            topo_order = list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            raise ScheduleValidationError(["Cannot perform forward pass: circular dependencies exist"])
        
        for node_id in topo_order:
            node = self.graph.nodes[node_id]
            duration = node['duration']
            
            # Find earliest start based on predecessors
            predecessors = list(self.graph.predecessors(node_id))
            
            if not predecessors:
                # No predecessors - start at project start
                early_start = self.project_start
            else:
                # ES = max(all predecessor constraints)
                candidate_starts = []
                for pred_id in predecessors:
                    pred_node = self.graph.nodes[pred_id]
                    pred_ef = pred_node['early_finish']
                    pred_es = pred_node['early_start']
                    edge_data = self.graph.edges[pred_id, node_id]
                    lag = edge_data.get('lag', 0)
                    rel_type = edge_data.get('pred_type', 'PR_FS')

                    if rel_type == 'PR_SS':
                        # ES(succ) >= ES(pred) + lag
                        candidate_start = self._days_to_work_date(pred_es, lag)
                    elif rel_type == 'PR_FF':
                        # EF(succ) >= EF(pred) + lag => ES(succ) >= EF(pred)+lag-duration
                        required_finish = self._days_to_work_date(pred_ef, lag)
                        candidate_start = self._days_to_work_date(required_finish, -duration)
                    elif rel_type == 'PR_SF':
                        # EF(succ) >= ES(pred) + lag => ES(succ) >= ES(pred)+lag-duration
                        required_finish = self._days_to_work_date(pred_es, lag)
                        candidate_start = self._days_to_work_date(required_finish, -duration)
                    else:
                        # FS: ES(succ) >= EF(pred) + lag
                        candidate_start = self._days_to_work_date(pred_ef, lag)

                    candidate_starts.append(candidate_start)
                
                early_start = max(candidate_starts)
            
            # Apply "Start On or After" constraint
            constraint_type = node.get('constraint_type')
            constraint_date = self._coerce_date(node.get('constraint_date'))
            
            if constraint_type in ('CS_MSOA', 'CS_SNET') and constraint_date:
                if constraint_date > early_start:
                    early_start = constraint_date
            
            # Calculate early finish
            early_finish = self._days_to_work_date(early_start, duration)
            
            # Store results
            node['early_start'] = early_start
            node['early_finish'] = early_finish
    
    @logfire.instrument("network_calculator.backward_pass")
    def backward_pass(self) -> None:
        """
        Calculate Late Start (LS) and Late Finish (LF) dates.
        
        Algorithm:
        1. Reverse topological order
        2. For each activity:
           - LF = min(successor-derived finishes, project_finish)
           - LS = LF - duration
        """
        if self.graph is None:
            raise ValueError("Network not built")
        
        # Find project finish (max EF of all activities)
        project_finish = max(
            self.graph.nodes[n]['early_finish']
            for n in self.graph.nodes
        )
        
        # Reverse topological order
        topo_order = list(nx.topological_sort(self.graph))
        reverse_order = list(reversed(topo_order))
        
        for node_id in reverse_order:
            node = self.graph.nodes[node_id]
            duration = node['duration']
            
            # Find latest finish based on successors
            successors = list(self.graph.successors(node_id))
            
            if not successors:
                # No successors - finish at project finish
                late_finish = project_finish
            else:
                # LF = min(all successor constraints)
                candidate_finishes = []
                for succ_id in successors:
                    succ_node = self.graph.nodes[succ_id]
                    succ_ls = succ_node['late_start']
                    succ_lf = succ_node['late_finish']
                    edge_data = self.graph.edges[node_id, succ_id]
                    lag = edge_data.get('lag', 0)
                    rel_type = edge_data.get('pred_type', 'PR_FS')

                    if rel_type == 'PR_SS':
                        # LS(pred) <= LS(succ) - lag => LF(pred) <= LS(succ)-lag+dur(pred)
                        latest_start = self._days_to_work_date(succ_ls, -lag)
                        candidate_finish = self._days_to_work_date(latest_start, duration)
                    elif rel_type == 'PR_FF':
                        # LF(pred) <= LF(succ) - lag
                        candidate_finish = self._days_to_work_date(succ_lf, -lag)
                    elif rel_type == 'PR_SF':
                        # LS(pred) <= LF(succ) - lag => LF(pred) <= LF(succ)-lag+dur(pred)
                        latest_start = self._days_to_work_date(succ_lf, -lag)
                        candidate_finish = self._days_to_work_date(latest_start, duration)
                    else:
                        # FS: LF(pred) <= LS(succ) - lag
                        candidate_finish = self._days_to_work_date(succ_ls, -lag)

                    candidate_finishes.append(candidate_finish)
                
                late_finish = min(candidate_finishes)
            
            # Calculate late start (work backwards from late finish)
            # LS = LF - duration
            late_start = self._days_to_work_date(late_finish, -duration)
            
            # Store results
            node['late_start'] = late_start
            node['late_finish'] = late_finish
    
    @logfire.instrument("network_calculator.calculate_float")
    def calculate_float(self) -> None:
        """
        Calculate Total Float (TF) and Free Float (FF) for each activity.
        
        Total Float = LS - ES (or LF - EF)
        Free Float = min(ES of successors) - EF
        """
        if self.graph is None:
            raise ValueError("Network not built")
        
        for node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            
            # Total Float = LS - ES (in work days)
            total_float = self._work_days_between(node['early_start'], node['late_start'])
            
            # Free Float = min(ES of successors) - EF
            successors = list(self.graph.successors(node_id))
            if successors:
                min_succ_es = min(
                    self.graph.nodes[s]['early_start']
                    for s in successors
                )
                free_float = self._work_days_between(node['early_finish'], min_succ_es)
            else:
                free_float = total_float  # End activities: FF = TF
            
            node['total_float'] = max(0, total_float)
            node['free_float'] = max(0, free_float)
    
    @logfire.instrument("network_calculator.identify_critical_path")
    def identify_critical_path(self) -> list[int]:
        """
        Identify critical path activities (TF = 0 or near zero).
        
        Returns:
            List of task_ids on the critical path
        """
        if self.graph is None:
            raise ValueError("Network not built")
        
        # Critical activities have total float = 0 (or very close due to rounding)
        critical_ids = [
            node_id
            for node_id, attrs in self.graph.nodes(data=True)
            if attrs.get('total_float', float('inf')) < 0.5  # Allow small tolerance
        ]
        
        return critical_ids

    @logfire.instrument("network_calculator.validate_against_ms_dates")
    def validate_against_ms_dates(self, tolerance_days: int = 1) -> dict:
        """
        Compare calculated dates against stored MS dates (ground truth).

        Returns:
            Summary with total/matched counts and discrepancy list.
        """
        if self.graph is None:
            raise ValueError("Network not built")

        if self.activities_df.empty or 'task_id' not in self.activities_df.columns:
            return {
                'total_compared': 0,
                'matched': 0,
                'match_rate': 0.0,
                'discrepancies': [],
            }

        df = self.activities_df.copy()
        if 'original_start' not in df.columns:
            if 'target_start_date' in df.columns:
                df['original_start'] = df['target_start_date']
            else:
                df['original_start'] = None

        if 'original_finish' not in df.columns:
            if 'target_end_date' in df.columns:
                df['original_finish'] = df['target_end_date']
            else:
                df['original_finish'] = None

        lookup = df.set_index('task_id')
        discrepancies: list[dict] = []
        matched = 0
        total = 0

        for node_id, attrs in self.graph.nodes(data=True):
            if node_id not in lookup.index:
                continue

            row = lookup.loc[node_id]
            expected_start = self._coerce_date(row.get('original_start'))
            expected_finish = self._coerce_date(row.get('original_finish'))
            calc_start = self._coerce_date(attrs.get('early_start'))
            calc_finish = self._coerce_date(attrs.get('early_finish'))

            if expected_start is None and expected_finish is None:
                continue

            start_delta = abs((calc_start - expected_start).days) if calc_start and expected_start else None
            finish_delta = abs((calc_finish - expected_finish).days) if calc_finish and expected_finish else None

            start_ok = start_delta is None or start_delta <= tolerance_days
            finish_ok = finish_delta is None or finish_delta <= tolerance_days
            is_match = bool(start_ok and finish_ok)

            total += 1
            if is_match:
                matched += 1
            else:
                discrepancies.append({
                    'task_id': int(node_id),
                    'task_code': str(attrs.get('task_code', '')),
                    'task_name': str(attrs.get('task_name', '')),
                    'start_delta_days': start_delta,
                    'finish_delta_days': finish_delta,
                    'expected_start': expected_start.isoformat() if expected_start else None,
                    'expected_finish': expected_finish.isoformat() if expected_finish else None,
                    'calculated_start': calc_start.isoformat() if calc_start else None,
                    'calculated_finish': calc_finish.isoformat() if calc_finish else None,
                })

            logfire.info(
                "MS date comparison",
                task_id=int(node_id),
                task_code=str(attrs.get('task_code', '')),
                match=is_match,
                start_delta_days=start_delta,
                finish_delta_days=finish_delta,
                expected_start=expected_start.isoformat() if expected_start else None,
                expected_finish=expected_finish.isoformat() if expected_finish else None,
                calculated_start=calc_start.isoformat() if calc_start else None,
                calculated_finish=calc_finish.isoformat() if calc_finish else None,
            )

        match_rate = (matched / total) if total else 0.0
        return {
            'total_compared': total,
            'matched': matched,
            'match_rate': match_rate,
            'discrepancies': discrepancies,
        }
    
    @logfire.instrument("network_calculator.calculate")
    def calculate(self) -> CalculationResult:
        """
        Run full CPM calculation and return results.
        
        Steps:
        1. Build network
        2. Validate network
        3. Forward pass (ES, EF)
        4. Backward pass (LS, LF)
        5. Calculate float
        6. Identify critical path
        
        Returns:
            CalculationResult with all calculated activities
        """
        # Build network
        self.build_network()
        
        # Validate
        errors = self.validate_network()
        if errors:
            raise ScheduleValidationError(errors)
        
        # Handle empty schedule
        if len(self.graph.nodes) == 0:
            return CalculationResult(
                activities=[],
                project_start=self.project_start,
                project_finish=self.project_start,
                critical_path_ids=[],
                critical_path_length_days=0,
                warnings=self._warnings
            )
        
        # CPM passes
        self.forward_pass()
        self.backward_pass()
        self.calculate_float()
        
        # Identify critical path
        critical_ids = self.identify_critical_path()
        
        # Build results
        activities = []
        for node_id, attrs in self.graph.nodes(data=True):
            activities.append(CalculatedActivity(
                task_id=node_id,
                task_code=attrs['task_code'],
                task_name=attrs['task_name'],
                wbs_id=attrs.get('wbs_id'),
                wbs_path=attrs.get('wbs_path'),
                duration_days=attrs['duration'],
                early_start=attrs['early_start'],
                early_finish=attrs['early_finish'],
                late_start=attrs['late_start'],
                late_finish=attrs['late_finish'],
                total_float_days=attrs['total_float'],
                free_float_days=attrs['free_float'],
                is_critical=node_id in critical_ids,
                status=attrs['status'],
                constraint_type=attrs.get('constraint_type'),
                constraint_date=attrs.get('constraint_date'),
            ))
        
        # Calculate project dates and critical path length
        project_start = min(a.early_start for a in activities)
        project_finish = max(a.early_finish for a in activities)
        critical_path_length = self._work_days_between(project_start, project_finish)
        
        return CalculationResult(
            activities=activities,
            project_start=project_start,
            project_finish=project_finish,
            critical_path_ids=critical_ids,
            critical_path_length_days=critical_path_length,
            warnings=self._warnings
        )
