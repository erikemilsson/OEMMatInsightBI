"""
Performance Monitoring Module for OEMMatInsightBI Pipeline

This module provides functions to track, analyze, and report on pipeline performance metrics.
Can be imported into Fabric notebooks or run standalone for performance analysis.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json


class PerformanceMonitor:
    """Monitor and track pipeline performance metrics"""

    def __init__(self, lakehouse_path: str = "/lakehouse/default"):
        """Initialize performance monitor with lakehouse path"""
        self.lakehouse_path = lakehouse_path
        self.metrics_table = f"{lakehouse_path}/Tables/performance_metrics"
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Load performance thresholds"""
        return {
            'bronze_ingestion': {'warning': 300, 'critical': 600},  # seconds
            'silver_transformation': {'warning': 420, 'critical': 840},
            'gold_creation': {'warning': 600, 'critical': 1200},
            'warehouse_load': {'warning': 300, 'critical': 600},
            'end_to_end': {'warning': 1800, 'critical': 3600}
        }

    def track_execution(
        self,
        pipeline_name: str,
        step_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        rows_processed: int = 0,
        status: str = 'Running',
        error_message: Optional[str] = None
    ) -> Dict:
        """Track pipeline execution metrics"""
        if end_time is None:
            end_time = datetime.now()

        duration_sec = (end_time - start_time).total_seconds()
        rows_per_sec = rows_processed / duration_sec if duration_sec > 0 else 0

        metric = {
            'pipeline_name': pipeline_name,
            'step_name': step_name,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_sec': duration_sec,
            'duration_min': duration_sec / 60,
            'rows_processed': rows_processed,
            'rows_per_sec': rows_per_sec,
            'status': status,
            'error_message': error_message,
            'recorded_at': datetime.now().isoformat()
        }

        # Check performance thresholds
        if step_name in self.thresholds:
            if duration_sec > self.thresholds[step_name]['critical']:
                metric['performance_status'] = 'Critical'
            elif duration_sec > self.thresholds[step_name]['warning']:
                metric['performance_status'] = 'Warning'
            else:
                metric['performance_status'] = 'Good'

        return metric

    def calculate_kpis(self, metrics: List[Dict]) -> Dict:
        """Calculate Key Performance Indicators from metrics"""
        if not metrics:
            return {}

        durations = [m['duration_min'] for m in metrics if 'duration_min' in m]
        success_count = sum(1 for m in metrics if m.get('status') == 'Success')
        total_count = len(metrics)

        kpis = {
            'total_runs': total_count,
            'success_rate': (success_count / total_count * 100) if total_count > 0 else 0,
            'avg_duration_min': sum(durations) / len(durations) if durations else 0,
            'min_duration_min': min(durations) if durations else 0,
            'max_duration_min': max(durations) if durations else 0,
            'total_rows_processed': sum(m.get('rows_processed', 0) for m in metrics),
            'avg_rows_per_sec': sum(m.get('rows_per_sec', 0) for m in metrics) / len(metrics) if metrics else 0
        }

        # Calculate percentiles
        if durations:
            sorted_durations = sorted(durations)
            p50_idx = int(len(sorted_durations) * 0.5)
            p95_idx = int(len(sorted_durations) * 0.95)
            kpis['p50_duration_min'] = sorted_durations[p50_idx] if p50_idx < len(sorted_durations) else 0
            kpis['p95_duration_min'] = sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else 0

        return kpis

    def get_bottlenecks(self, metrics: List[Dict], top_n: int = 5) -> List[Dict]:
        """Identify performance bottlenecks"""
        step_durations = {}

        for metric in metrics:
            step = metric.get('step_name', 'Unknown')
            duration = metric.get('duration_sec', 0)

            if step not in step_durations:
                step_durations[step] = []
            step_durations[step].append(duration)

        bottlenecks = []
        for step, durations in step_durations.items():
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            bottlenecks.append({
                'step_name': step,
                'avg_duration_sec': avg_duration,
                'max_duration_sec': max_duration,
                'run_count': len(durations),
                'total_time_sec': sum(durations)
            })

        # Sort by total time consumed
        bottlenecks.sort(key=lambda x: x['total_time_sec'], reverse=True)
        return bottlenecks[:top_n]

    def check_sla_compliance(self, metrics: List[Dict]) -> Dict:
        """Check SLA compliance for pipeline runs"""
        sla_targets = {
            'end_to_end': 30,  # minutes
            'bronze_ingestion': 5,
            'silver_transformation': 7,
            'gold_creation': 10,
            'warehouse_load': 5
        }

        compliance = {}
        for step, target_min in sla_targets.items():
            step_metrics = [m for m in metrics if m.get('step_name') == step]
            if step_metrics:
                violations = sum(1 for m in step_metrics if m.get('duration_min', 0) > target_min)
                total = len(step_metrics)
                compliance[step] = {
                    'target_min': target_min,
                    'total_runs': total,
                    'violations': violations,
                    'compliance_rate': ((total - violations) / total * 100) if total > 0 else 100
                }

        return compliance

    def generate_performance_report(self, metrics: List[Dict]) -> str:
        """Generate a performance report summary"""
        kpis = self.calculate_kpis(metrics)
        bottlenecks = self.get_bottlenecks(metrics)
        sla_compliance = self.check_sla_compliance(metrics)

        report = []
        report.append("=" * 60)
        report.append("PERFORMANCE REPORT")
        report.append("=" * 60)

        # KPIs Section
        report.append("\n📊 Key Performance Indicators:")
        report.append(f"  Total Runs: {kpis.get('total_runs', 0)}")
        report.append(f"  Success Rate: {kpis.get('success_rate', 0):.1f}%")
        report.append(f"  Avg Duration: {kpis.get('avg_duration_min', 0):.1f} min")
        report.append(f"  P50 Duration: {kpis.get('p50_duration_min', 0):.1f} min")
        report.append(f"  P95 Duration: {kpis.get('p95_duration_min', 0):.1f} min")
        report.append(f"  Total Rows: {kpis.get('total_rows_processed', 0):,}")
        report.append(f"  Avg Throughput: {kpis.get('avg_rows_per_sec', 0):.0f} rows/sec")

        # Bottlenecks Section
        report.append("\n🚨 Top Performance Bottlenecks:")
        for i, bottleneck in enumerate(bottlenecks[:3], 1):
            report.append(f"  {i}. {bottleneck['step_name']}:")
            report.append(f"     Avg: {bottleneck['avg_duration_sec']:.0f}s, Max: {bottleneck['max_duration_sec']:.0f}s")

        # SLA Compliance Section
        report.append("\n📋 SLA Compliance:")
        for step, compliance_data in sla_compliance.items():
            status = "✅" if compliance_data['compliance_rate'] >= 95 else "⚠️"
            report.append(f"  {status} {step}: {compliance_data['compliance_rate']:.1f}% compliant")
            if compliance_data['violations'] > 0:
                report.append(f"     ({compliance_data['violations']} violations out of {compliance_data['total_runs']} runs)")

        report.append("\n" + "=" * 60)
        return "\n".join(report)


def create_monitoring_queries() -> Dict[str, str]:
    """Create SQL queries for performance monitoring"""
    queries = {
        'recent_performance': """
            SELECT
                pipeline_name,
                step_name,
                start_time,
                end_time,
                duration_min,
                rows_processed,
                status,
                performance_status
            FROM performance_metrics
            WHERE start_time >= DATEADD(day, -7, GETDATE())
            ORDER BY start_time DESC
        """,

        'daily_summary': """
            SELECT
                DATE(start_time) as run_date,
                pipeline_name,
                COUNT(*) as run_count,
                AVG(duration_min) as avg_duration,
                MAX(duration_min) as max_duration,
                SUM(rows_processed) as total_rows,
                AVG(CASE WHEN status = 'Success' THEN 1.0 ELSE 0.0 END) * 100 as success_rate
            FROM performance_metrics
            WHERE start_time >= DATEADD(day, -30, GETDATE())
            GROUP BY DATE(start_time), pipeline_name
            ORDER BY run_date DESC
        """,

        'slow_queries': """
            SELECT
                step_name,
                start_time,
                duration_min,
                rows_processed,
                rows_per_sec,
                performance_status
            FROM performance_metrics
            WHERE performance_status IN ('Warning', 'Critical')
                AND start_time >= DATEADD(day, -7, GETDATE())
            ORDER BY duration_min DESC
            LIMIT 20
        """,

        'trend_analysis': """
            SELECT
                DATE(start_time) as run_date,
                step_name,
                AVG(duration_sec) as avg_duration_sec,
                AVG(duration_sec) - LAG(AVG(duration_sec)) OVER (PARTITION BY step_name ORDER BY DATE(start_time)) as duration_change
            FROM performance_metrics
            WHERE start_time >= DATEADD(day, -30, GETDATE())
            GROUP BY DATE(start_time), step_name
            ORDER BY run_date DESC, step_name
        """
    }
    return queries


# Example usage in Fabric notebook
def example_usage(spark):
    """Example of how to use the performance monitor in a Fabric notebook"""

    # Initialize monitor
    monitor = PerformanceMonitor()

    # Track pipeline execution
    start_time = datetime.now()

    # Your pipeline code here...
    # bronze_df = spark.read.table("bronze_procurement")
    # rows_count = bronze_df.count()

    end_time = datetime.now()

    # Record metrics
    metric = monitor.track_execution(
        pipeline_name="orchestrator_pipeline_bronze_to_gold",
        step_name="bronze_ingestion",
        start_time=start_time,
        end_time=end_time,
        rows_processed=45000,  # Example count
        status="Success"
    )

    # Generate report
    print(monitor.generate_performance_report([metric]))

    return metric


if __name__ == "__main__":
    # Test the module
    monitor = PerformanceMonitor()

    # Create sample metrics
    sample_metrics = [
        {
            'pipeline_name': 'test_pipeline',
            'step_name': 'bronze_ingestion',
            'duration_min': 3.5,
            'duration_sec': 210,
            'rows_processed': 50000,
            'rows_per_sec': 238,
            'status': 'Success'
        },
        {
            'pipeline_name': 'test_pipeline',
            'step_name': 'silver_transformation',
            'duration_min': 5.2,
            'duration_sec': 312,
            'rows_processed': 45000,
            'rows_per_sec': 144,
            'status': 'Success'
        }
    ]

    # Generate and print report
    report = monitor.generate_performance_report(sample_metrics)
    print(report)

    # Show monitoring queries
    queries = create_monitoring_queries()
    print("\nAvailable Monitoring Queries:")
    for name in queries.keys():
        print(f"  - {name}")