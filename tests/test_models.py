from hostfront_manager.models import CheckResult, DoctorReport


def test_doctor_report():
    report = DoctorReport([
        CheckResult("a", True, "ok"),
        CheckResult("b", False, "optional", critical=False),
    ])
    assert report.ok is True
    assert len(report.failed) == 1
