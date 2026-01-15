"""
Unit tests for the performance monitoring module
"""

import pytest
from datetime import datetime, timedelta
from src.monitoring.performance_monitor import PerformanceMonitor, create_monitoring_queries


class TestPerformanceMonitor:
    """Test cases for PerformanceMonitor class"""

    def test_monitor_initialization(self):
        """Test that monitor initializes with correct thresholds"""
        monitor = PerformanceMonitor()
        assert 'bronze_ingestion' in monitor.thresholds
        assert monitor.thresholds['bronze_ingestion']['warning'] == 300
        assert monitor.thresholds['bronze_ingestion']['critical'] == 600

    def test_track_execution_good_performance(self):
        """Test tracking execution with good performance"""
        monitor = PerformanceMonitor()
        start = datetime.now()
        end = start + timedelta(seconds=120)  # 2 minutes

        metric = monitor.track_execution(
            pipeline_name="test_pipeline",
            step_name="bronze_ingestion",
            start_time=start,
            end_time=end,
            rows_processed=10000,
            status="Success"
        )

        assert metric['pipeline_name'] == "test_pipeline"
        assert metric['duration_sec'] == 120
        assert metric['duration_min'] == 2.0
        assert metric['rows_per_sec'] == 10000 / 120
        assert metric['performance_status'] == 'Good'

    def test_track_execution_warning_performance(self):
        """Test tracking execution with warning-level performance"""
        monitor = PerformanceMonitor()
        start = datetime.now()
        end = start + timedelta(seconds=400)  # Over warning threshold

        metric = monitor.track_execution(
            pipeline_name="test_pipeline",
            step_name="bronze_ingestion",
            start_time=start,
            end_time=end,
            rows_processed=10000,
            status="Success"
        )

        assert metric['performance_status'] == 'Warning'

    def test_track_execution_critical_performance(self):
        """Test tracking execution with critical performance issues"""
        monitor = PerformanceMonitor()
        start = datetime.now()
        end = start + timedelta(seconds=700)  # Over critical threshold

        metric = monitor.track_execution(
            pipeline_name="test_pipeline",
            step_name="bronze_ingestion",
            start_time=start,
            end_time=end,
            rows_processed=10000,
            status="Success"
        )

        assert metric['performance_status'] == 'Critical'

    def test_calculate_kpis_empty_metrics(self):
        """Test KPI calculation with empty metrics"""
        monitor = PerformanceMonitor()
        kpis = monitor.calculate_kpis([])
        assert kpis == {}

    def test_calculate_kpis_with_metrics(self):
        """Test KPI calculation with sample metrics"""
        monitor = PerformanceMonitor()
        metrics = [
            {'duration_min': 2.0, 'status': 'Success', 'rows_processed': 1000, 'rows_per_sec': 100},
            {'duration_min': 3.0, 'status': 'Success', 'rows_processed': 2000, 'rows_per_sec': 150},
            {'duration_min': 4.0, 'status': 'Failed', 'rows_processed': 0, 'rows_per_sec': 0}
        ]

        kpis = monitor.calculate_kpis(metrics)

        assert kpis['total_runs'] == 3
        assert kpis['success_rate'] == pytest.approx(66.67, 0.01)
        assert kpis['avg_duration_min'] == 3.0
        assert kpis['min_duration_min'] == 2.0
        assert kpis['max_duration_min'] == 4.0
        assert kpis['total_rows_processed'] == 3000

    def test_get_bottlenecks(self):
        """Test bottleneck identification"""
        monitor = PerformanceMonitor()
        metrics = [
            {'step_name': 'bronze', 'duration_sec': 100},
            {'step_name': 'bronze', 'duration_sec': 120},
            {'step_name': 'silver', 'duration_sec': 500},
            {'step_name': 'silver', 'duration_sec': 550},
            {'step_name': 'gold', 'duration_sec': 200}
        ]

        bottlenecks = monitor.get_bottlenecks(metrics, top_n=2)

        assert len(bottlenecks) == 2
        assert bottlenecks[0]['step_name'] == 'silver'  # Highest total time
        assert bottlenecks[0]['total_time_sec'] == 1050
        assert bottlenecks[1]['step_name'] == 'bronze'

    def test_check_sla_compliance_all_compliant(self):
        """Test SLA compliance check with all compliant runs"""
        monitor = PerformanceMonitor()
        metrics = [
            {'step_name': 'bronze_ingestion', 'duration_min': 3},
            {'step_name': 'bronze_ingestion', 'duration_min': 4},
            {'step_name': 'silver_transformation', 'duration_min': 5}
        ]

        compliance = monitor.check_sla_compliance(metrics)

        assert compliance['bronze_ingestion']['compliance_rate'] == 100
        assert compliance['bronze_ingestion']['violations'] == 0

    def test_check_sla_compliance_with_violations(self):
        """Test SLA compliance check with violations"""
        monitor = PerformanceMonitor()
        metrics = [
            {'step_name': 'bronze_ingestion', 'duration_min': 3},
            {'step_name': 'bronze_ingestion', 'duration_min': 6},  # Violation
            {'step_name': 'bronze_ingestion', 'duration_min': 7}   # Violation
        ]

        compliance = monitor.check_sla_compliance(metrics)

        assert compliance['bronze_ingestion']['violations'] == 2
        assert compliance['bronze_ingestion']['compliance_rate'] == pytest.approx(33.33, 0.01)

    def test_generate_performance_report(self):
        """Test performance report generation"""
        monitor = PerformanceMonitor()
        metrics = [
            {
                'step_name': 'bronze_ingestion',
                'duration_min': 3,
                'duration_sec': 180,
                'status': 'Success',
                'rows_processed': 10000,
                'rows_per_sec': 55.56
            }
        ]

        report = monitor.generate_performance_report(metrics)

        assert "PERFORMANCE REPORT" in report
        assert "Key Performance Indicators" in report
        assert "Success Rate: 100.0%" in report
        assert "Top Performance Bottlenecks" in report

    def test_create_monitoring_queries(self):
        """Test that monitoring queries are created"""
        queries = create_monitoring_queries()

        assert 'recent_performance' in queries
        assert 'daily_summary' in queries
        assert 'slow_queries' in queries
        assert 'trend_analysis' in queries

        # Check that queries contain expected keywords
        assert 'SELECT' in queries['recent_performance']
        assert 'performance_metrics' in queries['recent_performance']


class TestPerformanceMonitorEdgeCases:
    """Test edge cases and error handling"""

    def test_zero_duration_handling(self):
        """Test handling of zero duration"""
        monitor = PerformanceMonitor()
        start = datetime.now()

        metric = monitor.track_execution(
            pipeline_name="test",
            step_name="test_step",
            start_time=start,
            end_time=start,  # Same as start
            rows_processed=1000
        )

        assert metric['duration_sec'] == 0
        assert metric['rows_per_sec'] == 0  # Should not divide by zero

    def test_missing_step_threshold(self):
        """Test behavior when step has no defined threshold"""
        monitor = PerformanceMonitor()
        start = datetime.now()
        end = start + timedelta(seconds=100)

        metric = monitor.track_execution(
            pipeline_name="test",
            step_name="unknown_step",  # Not in thresholds
            start_time=start,
            end_time=end,
            rows_processed=1000
        )

        assert 'performance_status' not in metric  # Should not have status

    def test_percentile_calculation_single_metric(self):
        """Test percentile calculation with single metric"""
        monitor = PerformanceMonitor()
        metrics = [{'duration_min': 5.0}]

        kpis = monitor.calculate_kpis(metrics)

        assert kpis['p50_duration_min'] == 5.0
        assert kpis['p95_duration_min'] == 5.0