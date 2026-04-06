"""
Advanced Performance Analysis Module

Provides calculations for:
- Latency spike/plateau detection
- Bottleneck identification
- Throughput analysis
- Batch behavior analysis
- Performance cockpit summary
"""

import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import json


class LatencyAnalyzer:
    """Analyze latency patterns to identify bottlenecks, spikes, and plateaus."""
    
    def __init__(self, performance_data: List[Dict]):
        """
        Initialize with performance data.
        Each entry should have: timestamp, source_latency, handling_latency, target_latency
        """
        self.data = sorted(performance_data, key=lambda x: x.get('timestamp') or datetime.min)
        self.source_latencies = [d.get('source_latency', 0) for d in self.data]
        self.handling_latencies = [d.get('handling_latency', 0) for d in self.data]
        self.target_latencies = [d.get('target_latency', 0) for d in self.data]
    
    def calculate_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Calculate key percentiles for a list of values."""
        if not values:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0, "min": 0, "avg": 0}
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        
        return {
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "avg": statistics.mean(sorted_vals),
            "p50": sorted_vals[int(n * 0.50)] if n > 0 else 0,
            "p90": sorted_vals[int(n * 0.90)] if n > 1 else sorted_vals[-1],
            "p95": sorted_vals[int(n * 0.95)] if n > 1 else sorted_vals[-1],
            "p99": sorted_vals[int(n * 0.99)] if n > 1 else sorted_vals[-1],
        }
    
    def get_latency_profile(self) -> Dict[str, Any]:
        """Get comprehensive latency profile with percentiles."""
        return {
            "source": self.calculate_percentiles(self.source_latencies),
            "handling": self.calculate_percentiles(self.handling_latencies),
            "target": self.calculate_percentiles(self.target_latencies),
            "data_points": len(self.data)
        }
    
    def identify_bottleneck(self) -> str:
        """
        Identify which component is the primary latency bottleneck.
        Returns: 'source', 'handling', or 'balanced'
        """
        if not self.data:
            return "unknown"
        
        avg_source = statistics.mean(self.source_latencies) if self.source_latencies else 0
        avg_handling = statistics.mean(self.handling_latencies) if self.handling_latencies else 0
        
        # If one is significantly larger than the other (>60% of total)
        total = avg_source + avg_handling
        if total == 0:
            return "balanced"
        
        source_pct = avg_source / total
        
        if source_pct > 0.65:
            return "source"
        elif source_pct < 0.35:
            return "handling"
        else:
            return "balanced"
    
    def get_bottleneck_analysis(self) -> Dict[str, Any]:
        """Detailed bottleneck analysis with time periods."""
        if len(self.data) < 2:
            return {"overall_bottleneck": "unknown", "periods": []}
        
        bottleneck = self.identify_bottleneck()
        
        # Analyze bottleneck by time periods
        periods = []
        window_size = max(5, len(self.data) // 10)  # ~10 periods
        
        for i in range(0, len(self.data), window_size):
            window = self.data[i:i + window_size]
            if not window:
                continue
            
            src_avg = statistics.mean([d.get('source_latency', 0) for d in window])
            hdl_avg = statistics.mean([d.get('handling_latency', 0) for d in window])
            total = src_avg + hdl_avg
            
            if total > 0:
                src_pct = src_avg / total
                period_bottleneck = "source" if src_pct > 0.65 else "handling" if src_pct < 0.35 else "balanced"
            else:
                period_bottleneck = "balanced"
            
            periods.append({
                "start_idx": i,
                "end_idx": min(i + window_size, len(self.data)),
                "start_time": window[0].get('timestamp').isoformat() if window[0].get('timestamp') else None,
                "end_time": window[-1].get('timestamp').isoformat() if window[-1].get('timestamp') else None,
                "source_avg": round(src_avg, 2),
                "handling_avg": round(hdl_avg, 2),
                "bottleneck": period_bottleneck
            })
        
        return {
            "overall_bottleneck": bottleneck,
            "periods": periods
        }
    
    def detect_spikes(self, threshold_multiplier: float = 2.5) -> List[Dict]:
        """
        Detect latency spikes (sudden increases > threshold_multiplier * rolling average).
        """
        if len(self.data) < 5:
            return []
        
        spikes = []
        window_size = 5
        
        for i in range(window_size, len(self.data)):
            # Calculate rolling average for target latency
            window_avg = statistics.mean(
                [d.get('target_latency', 0) for d in self.data[i-window_size:i]]
            )
            current = self.data[i].get('target_latency', 0)
            
            # Check for spike
            if window_avg > 0 and current > window_avg * threshold_multiplier:
                # Determine if spike is source or handling driven
                src_delta = self.data[i].get('source_latency', 0) - statistics.mean(
                    [d.get('source_latency', 0) for d in self.data[i-window_size:i]]
                )
                hdl_delta = self.data[i].get('handling_latency', 0) - statistics.mean(
                    [d.get('handling_latency', 0) for d in self.data[i-window_size:i]]
                )
                
                spike_driver = "source" if src_delta > hdl_delta else "handling"
                
                spikes.append({
                    "index": i,
                    "line_number": self.data[i].get('line_number'),
                    "timestamp": self.data[i].get('timestamp').isoformat() if self.data[i].get('timestamp') else None,
                    "value": round(current, 2),
                    "baseline": round(window_avg, 2),
                    "multiplier": round(current / window_avg, 1),
                    "driver": spike_driver,
                    "source_latency": round(self.data[i].get('source_latency', 0), 2),
                    "handling_latency": round(self.data[i].get('handling_latency', 0), 2)
                })
        
        return spikes
    
    def detect_plateaus(self, duration_threshold: int = 10, value_variance_pct: float = 0.15) -> List[Dict]:
        """
        Detect plateaus (extended periods where latency stays high with low variance).
        duration_threshold: minimum number of data points for a plateau
        value_variance_pct: max coefficient of variation (std/mean) to consider it a plateau
        """
        if len(self.data) < duration_threshold:
            return []
        
        plateaus = []
        overall_avg = statistics.mean(self.target_latencies) if self.target_latencies else 0
        
        i = 0
        while i < len(self.data) - duration_threshold:
            window = self.target_latencies[i:i + duration_threshold]
            window_avg = statistics.mean(window)
            window_std = statistics.stdev(window) if len(window) > 1 else 0
            cv = window_std / window_avg if window_avg > 0 else 1
            
            # Check if this is a high plateau (above average and low variance)
            if window_avg > overall_avg * 1.3 and cv < value_variance_pct:
                # Extend plateau as far as it goes
                end_idx = i + duration_threshold
                while end_idx < len(self.data):
                    extended_window = self.target_latencies[i:end_idx + 1]
                    ext_avg = statistics.mean(extended_window)
                    ext_std = statistics.stdev(extended_window) if len(extended_window) > 1 else 0
                    ext_cv = ext_std / ext_avg if ext_avg > 0 else 1
                    
                    if ext_cv < value_variance_pct * 1.5 and ext_avg > overall_avg:
                        end_idx += 1
                    else:
                        break
                
                plateaus.append({
                    "start_idx": i,
                    "end_idx": end_idx,
                    "start_time": self.data[i].get('timestamp').isoformat() if self.data[i].get('timestamp') else None,
                    "end_time": self.data[end_idx - 1].get('timestamp').isoformat() if self.data[end_idx - 1].get('timestamp') else None,
                    "start_line": self.data[i].get('line_number'),
                    "end_line": self.data[end_idx - 1].get('line_number'),
                    "duration_points": end_idx - i,
                    "avg_latency": round(statistics.mean(self.target_latencies[i:end_idx]), 2),
                    "variance_pct": round(cv * 100, 1)
                })
                
                i = end_idx
            else:
                i += 1
        
        return plateaus


class BatchAnalyzer:
    """Analyze batch behavior and closure patterns."""
    
    def __init__(self, batches: List[Dict]):
        """
        Initialize with batch data.
        Each entry should have: closure_reason, duration_seconds, changes_count, tables
        """
        self.batches = batches
    
    def get_closure_reason_distribution(self) -> Dict[str, int]:
        """Get count of batches by closure reason."""
        distribution = defaultdict(int)
        for batch in self.batches:
            reason = batch.get('closure_reason', 'Normal')
            distribution[reason] += 1
        return dict(distribution)
    
    def get_batch_size_stats(self) -> Dict[str, Any]:
        """Analyze batch sizes (changes per batch)."""
        sizes = [b.get('changes_count', 0) for b in self.batches if b.get('changes_count')]
        if not sizes:
            return {"count": 0}
        
        return {
            "count": len(sizes),
            "min": min(sizes),
            "max": max(sizes),
            "avg": round(statistics.mean(sizes), 1),
            "median": statistics.median(sizes),
            "total_changes": sum(sizes),
            "single_record_batches": sum(1 for s in sizes if s == 1),
            "single_record_pct": round(sum(1 for s in sizes if s == 1) / len(sizes) * 100, 1) if sizes else 0
        }
    
    def get_batch_duration_stats(self) -> Dict[str, Any]:
        """Analyze batch durations."""
        durations = [b.get('duration_seconds', 0) for b in self.batches if b.get('duration_seconds')]
        if not durations:
            return {"count": 0}
        
        return {
            "count": len(durations),
            "min": round(min(durations), 2),
            "max": round(max(durations), 2),
            "avg": round(statistics.mean(durations), 2),
            "median": round(statistics.median(durations), 2),
            "p95": round(sorted(durations)[int(len(durations) * 0.95)], 2) if len(durations) > 1 else durations[0]
        }
    
    def get_batch_analysis(self) -> Dict[str, Any]:
        """Complete batch analysis."""
        return {
            "total_batches": len(self.batches),
            "closure_reasons": self.get_closure_reason_distribution(),
            "size_stats": self.get_batch_size_stats(),
            "duration_stats": self.get_batch_duration_stats()
        }
    
    def detect_inefficiencies(self) -> List[Dict]:
        """Detect batch behavior inefficiencies."""
        issues = []
        
        size_stats = self.get_batch_size_stats()
        closure_dist = self.get_closure_reason_distribution()
        
        # High single-record batch percentage
        if size_stats.get('single_record_pct', 0) > 20:
            issues.append({
                "type": "high_single_record",
                "severity": "warning" if size_stats['single_record_pct'] > 40 else "info",
                "title": "High Single-Record Batch Rate",
                "message": f"{size_stats['single_record_pct']}% of batches contain only 1 record",
                "recommendation": "Review for PK conflicts or very small transactions",
                "value": size_stats['single_record_pct']
            })
        
        # Too many PK conflicts
        pk_total = closure_dist.get('PKi', 0) + closure_dist.get('PKu', 0) + closure_dist.get('PKd', 0)
        if pk_total > len(self.batches) * 0.1:
            issues.append({
                "type": "pk_conflicts",
                "severity": "warning",
                "title": "Frequent PK Conflicts",
                "message": f"{pk_total} batches closed due to PK conflicts ({round(pk_total/len(self.batches)*100, 1)}%)",
                "recommendation": "Consider adjusting batch settings or reviewing source transaction patterns",
                "value": pk_total
            })
        
        # Too many timeout closures
        timeout_total = closure_dist.get('TIM', 0) + closure_dist.get('TMO', 0)
        if timeout_total > len(self.batches) * 0.3:
            issues.append({
                "type": "timeout_closures",
                "severity": "info",
                "title": "Many Timeout Closures",
                "message": f"{timeout_total} batches closed due to timeouts",
                "recommendation": "This is normal for CDC with low activity. Consider adjusting timeout if needed.",
                "value": timeout_total
            })
        
        return issues


class TablePerformanceAnalyzer:
    """Analyze per-table performance to identify pain tables."""
    
    def __init__(self, table_stats: List[Dict], apply_events: List[Dict] = None):
        """Initialize with table statistics and optional apply events."""
        self.table_stats = {t.get('table_name'): t for t in table_stats}
        self.apply_events = apply_events or []
    
    def get_pain_tables(self, limit: int = 10) -> List[Dict]:
        """
        Get tables ranked by performance impact.
        Ranking factors: total apply time, error count, one-by-one count
        """
        scored_tables = []
        
        for name, stats in self.table_stats.items():
            # Calculate pain score
            apply_time = stats.get('total_apply_time_seconds', 0)
            errors = stats.get('error_count', 0)
            obo_count = stats.get('one_by_one_count', 0)
            total_ops = stats.get('total_inserts', 0) + stats.get('total_updates', 0) + stats.get('total_deletes', 0)
            
            # Weighted score
            pain_score = apply_time + (errors * 10) + (obo_count * 5)
            
            scored_tables.append({
                "table_name": name,
                "pain_score": round(pain_score, 2),
                "total_apply_time": round(apply_time, 2),
                "total_operations": total_ops,
                "avg_apply_time": round(stats.get('avg_apply_time_seconds', 0), 3),
                "max_apply_time": round(stats.get('max_apply_time_seconds', 0), 2),
                "error_count": errors,
                "one_by_one_count": obo_count,
                "has_pk": stats.get('has_pk'),
                "merge_count": stats.get('total_merges', 0)
            })
        
        # Sort by pain score descending
        return sorted(scored_tables, key=lambda x: x['pain_score'], reverse=True)[:limit]
    
    def get_apply_method_breakdown(self) -> Dict[str, Dict]:
        """Get breakdown of apply methods by table."""
        methods_by_table = defaultdict(lambda: {"MERGE": 0, "INSERT": 0, "UPDATE": 0, "DELETE": 0, "ONE_BY_ONE": 0})
        
        for event in self.apply_events:
            table = event.get('table_name')
            method = event.get('apply_method', 'UNKNOWN')
            count = event.get('operation_count', 1)
            
            if table:
                methods_by_table[table][method] += count
        
        return dict(methods_by_table)


class ErrorCorrelationAnalyzer:
    """Analyze correlation between errors and latency periods."""
    
    def __init__(self, errors: List[Dict], performance_data: List[Dict]):
        self.errors = sorted(errors, key=lambda x: x.get('timestamp') or datetime.min)
        self.perf_data = sorted(performance_data, key=lambda x: x.get('timestamp') or datetime.min)
    
    def correlate_errors_with_latency(self) -> Dict[str, Any]:
        """
        Find errors that occurred during high latency periods.
        Returns correlation analysis results.
        """
        if not self.errors or not self.perf_data:
            return {"correlations": [], "summary": {}}
        
        # Calculate high latency threshold (p75 of target latency)
        target_latencies = [p.get('target_latency', 0) for p in self.perf_data]
        if not target_latencies:
            return {"correlations": [], "summary": {}}
        
        sorted_latencies = sorted(target_latencies)
        high_latency_threshold = sorted_latencies[int(len(sorted_latencies) * 0.75)]
        
        # Find high latency windows
        high_latency_windows = []
        window_start = None
        
        for i, perf in enumerate(self.perf_data):
            if perf.get('target_latency', 0) > high_latency_threshold:
                if window_start is None:
                    window_start = perf.get('timestamp')
            else:
                if window_start is not None:
                    high_latency_windows.append({
                        'start': window_start,
                        'end': self.perf_data[i-1].get('timestamp') if i > 0 else window_start
                    })
                    window_start = None
        
        # Don't forget the last window if still in high latency
        if window_start is not None:
            high_latency_windows.append({
                'start': window_start,
                'end': self.perf_data[-1].get('timestamp')
            })
        
        # Find errors within high latency windows
        correlated_errors = []
        errors_by_component = defaultdict(int)
        errors_by_type = defaultdict(int)
        
        for error in self.errors:
            error_ts = error.get('timestamp')
            if not error_ts:
                continue
            
            for window in high_latency_windows:
                if window['start'] and window['end']:
                    if window['start'] <= error_ts <= window['end']:
                        correlated_errors.append({
                            'timestamp': error_ts.isoformat() if error_ts else None,
                            'component': error.get('component'),
                            'text': error.get('text', '')[:200],
                            'line_number': error.get('line_number')
                        })
                        errors_by_component[error.get('component', 'UNKNOWN')] += 1
                        
                        # Classify error type
                        text = error.get('text', '').lower()
                        if 'reconnect' in text or 'connection' in text:
                            errors_by_type['connection'] += 1
                        elif 'timeout' in text:
                            errors_by_type['timeout'] += 1
                        elif 'memory' in text:
                            errors_by_type['memory'] += 1
                        elif 'sql_error' in text or 'sqlstate' in text:
                            errors_by_type['sql'] += 1
                        else:
                            errors_by_type['other'] += 1
                        break
        
        return {
            "high_latency_threshold": round(high_latency_threshold, 2),
            "high_latency_windows": len(high_latency_windows),
            "total_correlated_errors": len(correlated_errors),
            "errors_by_component": dict(errors_by_component),
            "errors_by_type": dict(errors_by_type),
            "sample_errors": correlated_errors[:10]  # Top 10 examples
        }
    
    def get_error_timeline(self) -> List[Dict]:
        """Get errors with their position in the latency timeline."""
        if not self.errors or not self.perf_data:
            return []
        
        timeline = []
        for error in self.errors[:50]:  # Limit to 50
            error_ts = error.get('timestamp')
            if not error_ts:
                continue
            
            # Find nearest latency reading
            nearest_latency = None
            for perf in self.perf_data:
                if perf.get('timestamp') and perf.get('timestamp') <= error_ts:
                    nearest_latency = perf.get('target_latency')
            
            timeline.append({
                'timestamp': error_ts.isoformat() if error_ts else None,
                'component': error.get('component'),
                'line_number': error.get('line_number'),
                'latency_at_time': nearest_latency
            })
        
        return timeline


class ApplyMethodAnalyzer:
    """Analyze MERGE vs standard bulk apply methods."""
    
    def __init__(self, table_stats: List[Dict]):
        self.table_stats = table_stats
    
    def get_merge_breakdown(self) -> Dict[str, Any]:
        """Get breakdown of MERGE vs standard bulk operations."""
        total_merges = 0
        total_standard = 0
        tables_with_merge = []
        tables_without_merge = []
        
        for stats in self.table_stats:
            merges = stats.get('total_merges', 0)
            standard = (stats.get('total_inserts', 0) + 
                       stats.get('total_updates', 0) + 
                       stats.get('total_deletes', 0))
            
            total_merges += merges
            total_standard += standard
            
            table_info = {
                'table_name': stats.get('table_name'),
                'merge_count': merges,
                'standard_count': standard,
                'total': merges + standard,
                'merge_percent': round(merges * 100 / (merges + standard), 1) if (merges + standard) > 0 else 0
            }
            
            if merges > 0:
                tables_with_merge.append(table_info)
            else:
                tables_without_merge.append(table_info)
        
        grand_total = total_merges + total_standard
        
        return {
            "summary": {
                "total_merge_operations": total_merges,
                "total_standard_operations": total_standard,
                "merge_percent": round(total_merges * 100 / grand_total, 1) if grand_total > 0 else 0,
                "tables_using_merge": len(tables_with_merge),
                "tables_not_using_merge": len(tables_without_merge)
            },
            "tables_with_merge": sorted(tables_with_merge, key=lambda x: x['merge_count'], reverse=True),
            "tables_without_merge": tables_without_merge,
            "merge_enabled": total_merges > 0
        }


class CDCPipelineAnalyzer:
    """Analyze CDC pipeline (Sorter) metrics."""
    
    def __init__(self, sorter_events: List[Dict] = None, performance_data: List[Dict] = None):
        self.sorter_events = sorter_events or []
        self.perf_data = performance_data or []
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get comprehensive CDC pipeline summary."""
        memory_events = [e for e in self.sorter_events if e.get('event_type') == 'memory_warning']
        overflow_events = [e for e in self.sorter_events if e.get('event_type') == 'overflow']
        disconnects = [e for e in self.sorter_events if e.get('event_type') == 'target_disconnect']
        reconnects = [e for e in self.sorter_events if e.get('event_type') == 'reconnect']
        
        health = "healthy"
        if len(overflow_events) > 0 or len(disconnects) > 5:
            health = "critical"
        elif len(memory_events) > 3 or len(disconnects) > 0:
            health = "warning"
        
        return {
            "memory_warnings": len(memory_events),
            "overflow_events": len(overflow_events),
            "disconnections": len(disconnects),
            "reconnections": len(reconnects),
            "health_status": health,
            "has_issues": health != "healthy"
        }


# Oracle archived redo trace: only analyze reads strictly slower than this (ms)
ORACLE_REDO_MIN_MS = 200.0
# Flag when max duration is at least this multiple of min (e.g. 200 ms vs 400 ms)
ORACLE_REDO_MULTIPLIER_THRESHOLD = 2.0


def analyze_oracle_redo_read_variance(
    events: List[Dict],
    min_ms: float = ORACLE_REDO_MIN_MS,
    multiplier_threshold: float = ORACLE_REDO_MULTIPLIER_THRESHOLD,
) -> Dict[str, Any]:
    """
    Group similar archived redo reads (same byte size, thread, source location) and
    flag high variance when the slowest read is at least ``multiplier_threshold`` × the
    fastest, using only reads with duration strictly greater than ``min_ms``.
    """
    filtered = [e for e in events if float(e.get("read_ms") or 0) > min_ms]
    if not filtered:
        return {
            "min_read_ms_floor": min_ms,
            "multiplier_threshold": multiplier_threshold,
            "total_events": len(events),
            "total_events_over_floor": 0,
            "high_variance_groups": [],
            "has_red_flags": False,
        }

    groups: Dict[Tuple[Any, str, str], List[Dict]] = defaultdict(list)
    for e in filtered:
        key = (
            e.get("bytes_read"),
            str(e.get("thread_id") or ""),
            e.get("source_location") or "",
        )
        groups[key].append(e)

    high_variance_groups: List[Dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        ms_sorted = sorted(float(x.get("read_ms") or 0) for x in items)
        min_v, max_v = ms_sorted[0], ms_sorted[-1]
        if min_v <= 0:
            continue
        ratio = max_v / min_v
        if ratio < multiplier_threshold:
            continue
        bytes_read, thread_id, source_location = key
        samples = []
        for e in sorted(items, key=lambda x: float(x.get("read_ms") or 0)):
            ts = e.get("timestamp")
            if hasattr(ts, "isoformat"):
                ts_iso = ts.isoformat()
            else:
                ts_iso = str(ts) if ts is not None else None
            samples.append({
                "line_number": e.get("line_number"),
                "read_ms": round(float(e.get("read_ms") or 0), 1),
                "timestamp": ts_iso,
            })
        high_variance_groups.append({
            "bytes": bytes_read,
            "thread_id": thread_id or None,
            "source_location": source_location or None,
            "count": len(items),
            "min_ms": round(min_v, 1),
            "max_ms": round(max_v, 1),
            "multiplier": round(ratio, 2),
            "red_flag": True,
            "samples": samples,
        })

    high_variance_groups.sort(key=lambda g: g["multiplier"], reverse=True)

    return {
        "min_read_ms_floor": min_ms,
        "multiplier_threshold": multiplier_threshold,
        "total_events": len(events),
        "total_events_over_floor": len(filtered),
        "high_variance_groups": high_variance_groups[:15],
        "has_red_flags": len(high_variance_groups) > 0,
    }


def summarize_oracle_redo_log_sessions(sessions: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate statistics for paired Oracle redo log open→close sessions (seconds per log).
    """
    if not sessions:
        return {
            "session_count": 0,
            "duration_seconds_stats": None,
            "longest_sessions": [],
        }

    durations = [float(s["duration_seconds"]) for s in sessions]
    sorted_d = sorted(durations)
    n = len(sorted_d)

    def pct(p: float) -> float:
        if n == 0:
            return 0.0
        return sorted_d[min(int(n * p), n - 1)]

    duration_seconds_stats = {
        "min": round(min(durations), 3),
        "max": round(max(durations), 3),
        "avg": round(statistics.mean(durations), 3),
        "p95": round(pct(0.95), 3) if n > 1 else round(sorted_d[0], 3),
    }

    def path_tail(p: Optional[str]) -> str:
        if not p:
            return ""
        if len(p) <= 80:
            return p
        return "..." + p[-77:]

    longest = sorted(
        sessions,
        key=lambda x: float(x.get("duration_seconds") or 0),
        reverse=True,
    )[:5]
    longest_sessions = []
    for s in longest:
        longest_sessions.append({
            "duration_seconds": round(float(s.get("duration_seconds", 0)), 3),
            "line_open": s.get("line_open"),
            "line_close": s.get("line_close"),
            "thread_id": s.get("thread_id"),
            "redo_path_tail": path_tail(s.get("redo_path")),
        })

    return {
        "session_count": len(sessions),
        "duration_seconds_stats": duration_seconds_stats,
        "longest_sessions": longest_sessions,
    }


class SourceAnalyzer:
    """Analyze source-side metrics."""
    
    def __init__(self, source_events: List[Dict] = None, errors: List[Dict] = None, 
                 performance_data: List[Dict] = None):
        self.source_events = source_events or []
        self.errors = errors or []
        self.perf_data = performance_data or []
    
    def get_source_summary(self) -> Dict[str, Any]:
        """Get comprehensive source-side analysis summary."""
        reconnects = [e for e in self.source_events if e.get('event_type') == 'reconnect']
        source_errors = [e for e in self.errors if e.get('component', '').upper() in ['SOURCE_CAPTURE', 'SOURCE_UNLOAD', 'COMMON']]
        
        # Categorize errors
        network_issues = sum(1 for e in source_errors if any(x in e.get('text', '').lower() for x in ['network', 'socket', 'connection', 'timeout', 'refused']))
        contention_issues = sum(1 for e in source_errors if any(x in e.get('text', '').lower() for x in ['lock', 'contention', 'wait', 'blocked']))
        resource_issues = sum(1 for e in source_errors if any(x in e.get('text', '').lower() for x in ['memory', 'resource', 'limit']))
        
        hints = []
        if network_issues:
            hints.append("Network issues detected - check source connectivity")
        if contention_issues:
            hints.append("Database contention - review locks and transactions")
        if resource_issues:
            hints.append("Resource limitations - check server resources")
        
        health = "healthy"
        if network_issues > 5 or len(reconnects) > 5:
            health = "critical"
        elif len(source_errors) > 0 or len(reconnects) > 3:
            health = "warning"
        
        return {
            "total_reconnects": len(reconnects),
            "total_source_errors": len(source_errors),
            "network_issues": network_issues,
            "contention_issues": contention_issues,
            "resource_issues": resource_issues,
            "investigation_hints": hints,
            "health_status": health
        }


class PerformanceCockpit:
    """Generate a unified performance summary combining all analysis modules."""
    
    def __init__(
        self,
        performance_data: List[Dict],
        batches: List[Dict] = None,
        table_stats: List[Dict] = None,
        file_operations: List[Dict] = None,
        errors: List[Dict] = None,
        config: Dict = None,
        sorter_events: List[Dict] = None,
        source_events: List[Dict] = None,
        oracle_redo_reads: List[Dict] = None,
        oracle_redo_log_sessions: List[Dict] = None,
    ):
        self.performance_data = performance_data
        self.latency_analyzer = LatencyAnalyzer(performance_data)
        self.batch_analyzer = BatchAnalyzer(batches or [])
        self.table_analyzer = TablePerformanceAnalyzer(table_stats or [])
        self.error_correlation_analyzer = ErrorCorrelationAnalyzer(errors or [], performance_data)
        self.apply_method_analyzer = ApplyMethodAnalyzer(table_stats or [])
        self.cdc_pipeline_analyzer = CDCPipelineAnalyzer(sorter_events or [], performance_data)
        self.source_analyzer = SourceAnalyzer(source_events or [], errors or [], performance_data)
        self.file_operations = file_operations or []
        self.errors = errors or []
        self.config = config or {}
        self.oracle_redo_reads = oracle_redo_reads or []
        self.oracle_redo_log_sessions = oracle_redo_log_sessions or []
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate the complete performance cockpit summary."""
        
        # Latency analysis
        latency_profile = self.latency_analyzer.get_latency_profile()
        bottleneck_analysis = self.latency_analyzer.get_bottleneck_analysis()
        spikes = self.latency_analyzer.detect_spikes()
        plateaus = self.latency_analyzer.detect_plateaus()
        
        # Batch analysis
        batch_analysis = self.batch_analyzer.get_batch_analysis()
        batch_issues = self.batch_analyzer.detect_inefficiencies()
        
        # Table analysis
        pain_tables = self.table_analyzer.get_pain_tables(10)
        
        # File operations summary
        file_ops_summary = self._summarize_file_operations()
        
        # Top latency contributors
        contributors = self._identify_top_contributors()
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            bottleneck_analysis, spikes, plateaus, batch_issues, pain_tables
        )
        
        # Error correlation analysis
        error_correlation = self.error_correlation_analyzer.correlate_errors_with_latency()
        
        # MERGE vs standard bulk analysis
        merge_breakdown = self.apply_method_analyzer.get_merge_breakdown()
        
        # CDC Pipeline analysis
        cdc_pipeline = self.cdc_pipeline_analyzer.get_pipeline_summary()
        
        # Source-side analysis
        source_analysis = self.source_analyzer.get_source_summary()
        
        # Add source/pipeline recommendations
        recommendations = self._add_pipeline_recommendations(recommendations, cdc_pipeline, source_analysis)
        
        oracle_redo_log_processing = summarize_oracle_redo_log_sessions(self.oracle_redo_log_sessions)

        oracle_redo_read_analysis = analyze_oracle_redo_read_variance(self.oracle_redo_reads)
        if oracle_redo_read_analysis.get("has_red_flags"):
            recommendations.append({
                "priority": "high",
                "area": "Source",
                "title": "Oracle archived redo read time spread (trace)",
                "description": (
                    "Similar archived redo reads (same size, thread, and code path) show at least "
                    f"{ORACLE_REDO_MULTIPLIER_THRESHOLD:.0f}× difference in duration among reads slower than "
                    f"{ORACLE_REDO_MIN_MS:.0f} ms. Investigate source I/O, storage latency, and system load."
                ),
                "actions": [
                    "Review storage and redo log volume performance on the Oracle host",
                    "Check for concurrent I/O or CPU contention during slow reads",
                    "Compare slow vs fast sample line numbers in the log for timing correlation",
                ],
            })
        
        return {
            "latency_profile": latency_profile,
            "bottleneck": {
                "primary": bottleneck_analysis['overall_bottleneck'],
                "periods": bottleneck_analysis['periods'][:5]  # Top 5 periods
            },
            "spikes": {
                "count": len(spikes),
                "items": spikes[:10]  # Top 10 spikes
            },
            "plateaus": {
                "count": len(plateaus),
                "items": plateaus[:5]  # Top 5 plateaus
            },
            "batch_profile": batch_analysis,
            "batch_issues": batch_issues,
            "pain_tables": pain_tables,
            "file_operations": file_ops_summary,
            "top_contributors": contributors,
            "recommendations": recommendations,
            "config": self.config,
            "error_summary": {
                "total": len(self.errors),
                "by_component": self._group_errors_by_component()
            },
            "error_correlation": error_correlation,
            "merge_analysis": merge_breakdown,
            "cdc_pipeline": cdc_pipeline,
            "source_analysis": source_analysis,
            "oracle_redo_read_analysis": oracle_redo_read_analysis,
            "oracle_redo_log_processing": oracle_redo_log_processing,
        }
    
    def _summarize_file_operations(self) -> Dict[str, Any]:
        """Summarize file upload operations."""
        if not self.file_operations:
            return {"count": 0}
        
        sizes = [f.get('file_size_bytes', 0) for f in self.file_operations]
        upload_times = [f.get('upload_time_seconds', 0) for f in self.file_operations if f.get('upload_time_seconds')]
        throughputs = [f.get('throughput_kbps', 0) for f in self.file_operations if f.get('throughput_kbps')]
        
        return {
            "count": len(self.file_operations),
            "total_size_bytes": sum(sizes),
            "avg_size_bytes": round(statistics.mean(sizes), 0) if sizes else 0,
            "total_upload_time": round(sum(upload_times), 2),
            "avg_upload_time": round(statistics.mean(upload_times), 2) if upload_times else 0,
            "avg_throughput_kbps": round(statistics.mean(throughputs), 2) if throughputs else 0
        }
    
    def _identify_top_contributors(self) -> List[str]:
        """Identify top contributors to latency."""
        contributors = []
        
        # Check bottleneck
        bottleneck = self.latency_analyzer.identify_bottleneck()
        if bottleneck == "source":
            contributors.append("Source Capture")
        elif bottleneck == "handling":
            contributors.append("Target Apply")
        
        # Check file operations
        file_summary = self._summarize_file_operations()
        if file_summary.get('avg_upload_time', 0) > 1:
            contributors.append("File Uploads")
        
        # Check batch behavior
        batch_analysis = self.batch_analyzer.get_batch_analysis()
        pk_total = sum(batch_analysis['closure_reasons'].get(k, 0) for k in ['PKi', 'PKu', 'PKd'])
        if pk_total > batch_analysis['total_batches'] * 0.1:
            contributors.append("PK Conflicts")
        
        # Check pain tables
        pain_tables = self.table_analyzer.get_pain_tables(3)
        if pain_tables and pain_tables[0].get('pain_score', 0) > 100:
            contributors.append(f"Table: {pain_tables[0]['table_name']}")
        
        return contributors or ["Normal Operation"]
    
    def _group_errors_by_component(self) -> Dict[str, int]:
        """Group errors by component."""
        by_component = defaultdict(int)
        for err in self.errors:
            comp = err.get('component', 'UNKNOWN')
            by_component[comp] += 1
        return dict(by_component)
    
    def _generate_recommendations(
        self,
        bottleneck_analysis: Dict,
        spikes: List,
        plateaus: List,
        batch_issues: List,
        pain_tables: List
    ) -> List[Dict]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Bottleneck recommendations
        bottleneck = bottleneck_analysis['overall_bottleneck']
        if bottleneck == "source":
            recommendations.append({
                "priority": "high",
                "area": "Source",
                "title": "Source Capture Latency Dominates",
                "description": "Source capture is the primary bottleneck. Time spent reading from source exceeds time spent applying to target.",
                "actions": [
                    "Review source database query performance and load",
                    "Check network latency between Replicate and source",
                    "Review source endpoint configuration (e.g., batch read settings)",
                    "Consider increasing source capture threads if available"
                ]
            })
        elif bottleneck == "handling":
            recommendations.append({
                "priority": "high",
                "area": "Target",
                "title": "Target Apply Latency Dominates",
                "description": "Target apply (handling) is the primary bottleneck. Time spent applying changes to target exceeds source capture time.",
                "actions": [
                    "Check target database/endpoint performance",
                    "Review batch timeout and size settings (larger batches may help)",
                    "Check for slow operations (1-by-1 applies, PK updates)",
                    "Consider enabling parallel apply if not already"
                ]
            })
        
        # Spike recommendations
        if len(spikes) > 5:
            recommendations.append({
                "priority": "medium",
                "area": "Stability",
                "title": "Frequent Latency Spikes",
                "description": f"{len(spikes)} latency spikes detected. Investigate root cause.",
                "actions": [
                    "Check for concurrent heavy operations during spike times",
                    "Review network stability",
                    "Check for garbage collection or memory pressure"
                ]
            })
        
        # Plateau recommendations
        if plateaus:
            recommendations.append({
                "priority": "medium",
                "area": "Performance",
                "title": "Latency Plateaus Detected",
                "description": f"{len(plateaus)} periods of sustained high latency found.",
                "actions": [
                    "Investigate periods of flat high latency",
                    "Check for resource contention or throttling",
                    "Review if task was stuck or waiting"
                ]
            })
        
        # Batch issues
        for issue in batch_issues:
            if issue['severity'] == 'warning':
                recommendations.append({
                    "priority": "medium",
                    "area": "Batching",
                    "title": issue['title'],
                    "description": issue['message'],
                    "actions": [issue['recommendation']]
                })
        
        # Pain tables
        if pain_tables:
            top_pain = pain_tables[0]
            if top_pain.get('one_by_one_count', 0) > 10:
                recommendations.append({
                    "priority": "high",
                    "area": "Tables",
                    "title": f"Table {top_pain['table_name']} Has Issues",
                    "description": f"This table has {top_pain['one_by_one_count']} one-by-one apply operations.",
                    "actions": [
                        "Check if table has a primary key defined",
                        "Review data quality and constraints",
                        "Consider table-specific error handling settings"
                    ]
                })
        
        return recommendations
    
    def _add_pipeline_recommendations(
        self,
        recommendations: List[Dict],
        cdc_pipeline: Dict,
        source_analysis: Dict
    ) -> List[Dict]:
        """Add recommendations based on CDC pipeline and source analysis."""
        
        # CDC Pipeline issues
        if cdc_pipeline.get('health_status') == 'critical':
            recommendations.append({
                "priority": "high",
                "area": "Pipeline",
                "title": "Critical CDC Pipeline Issues",
                "description": f"Detected {cdc_pipeline.get('memory_warnings', 0)} memory warnings and {cdc_pipeline.get('disconnections', 0)} disconnections.",
                "actions": [
                    "Check sorter memory configuration",
                    "Review target connection stability",
                    "Consider increasing stream buffer settings"
                ]
            })
        elif cdc_pipeline.get('health_status') == 'warning':
            recommendations.append({
                "priority": "medium",
                "area": "Pipeline",
                "title": "CDC Pipeline Warnings",
                "description": "Sorter memory or connection issues detected.",
                "actions": [
                    "Monitor sorter memory usage",
                    "Review target connection health"
                ]
            })
        
        # Source-side issues
        if source_analysis.get('health_status') == 'critical':
            recommendations.append({
                "priority": "high",
                "area": "Source",
                "title": "Critical Source Issues",
                "description": f"Detected {source_analysis.get('network_issues', 0)} network issues and {source_analysis.get('total_reconnects', 0)} reconnections.",
                "actions": source_analysis.get('investigation_hints', [
                    "Check source database connectivity",
                    "Review network stability"
                ])
            })
        elif source_analysis.get('health_status') == 'warning':
            if source_analysis.get('investigation_hints'):
                recommendations.append({
                    "priority": "medium",
                    "area": "Source",
                    "title": "Source Issues Detected",
                    "description": f"{source_analysis.get('total_source_errors', 0)} source-related errors found.",
                    "actions": source_analysis.get('investigation_hints', [])
                })
        
        return recommendations

