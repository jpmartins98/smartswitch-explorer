from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
import pytest

from gui.ui import landing_page


def test_empty_refresh_clears_stale_results_and_finishes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    page = landing_page.LandingPage()
    monkeypatch.setattr(landing_page, "discover_backup_roots", lambda: [])
    page.set_recent_backups([tmp_path / "removed-backup"])
    page.backup_list.addItem("stale backup")
    events: list[str] = []
    page.listing_started.connect(lambda: events.append("started"))
    page.listing_finished.connect(lambda: events.append("finished"))
    try:
        page.refresh()
        page.refresh()
        assert events == ["started", "finished", "started", "finished"]
        assert page.backup_list.count() == 0
        assert page.backup_list.isHidden()
        assert not page.empty_state.isHidden()
        assert not page._refresh_running
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("scan_error", [False, True])
def test_queued_refresh_completes_after_worker_result_or_error(monkeypatch, tmp_path, scan_error) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    page = landing_page.LandingPage()
    monkeypatch.setattr(landing_page, "discover_backup_roots", lambda: [tmp_path])
    if scan_error:
        def fail_scan(_root):
            raise OSError("unreadable backup root")
        monkeypatch.setattr(landing_page, "find_backups", fail_scan)
    events: list[str] = []
    errors: list[str] = []
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    page.listing_started.connect(lambda: events.append("started"))
    page.listing_error.connect(errors.append)

    def finished():
        events.append("finished")
        if events.count("finished") == 2:
            loop.quit()

    page.listing_finished.connect(finished)
    try:
        page.refresh()
        page.refresh()
        timer.start(5000)
        loop.exec()
        assert events == ["started", "finished", "started", "finished"]
        assert len(errors) == (2 if scan_error else 0)
        if scan_error:
            assert all("unreadable backup root" in error for error in errors)
        assert not page._refresh_running
        assert not page._refresh_pending
        assert page.backup_list.count() == 0
    finally:
        timer.stop()
        page._thread_pool.waitForDone()
        page.close()
        page.deleteLater()
        app.processEvents()
