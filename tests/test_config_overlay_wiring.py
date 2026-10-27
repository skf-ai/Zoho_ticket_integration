"""Overlay-aware knowledge/holidays/SLA: each falls back to its bundled
default whenever the SKF Admin Console's override is unset (the normal case
in this test suite, since SKF_ADMIN_CONFIG_TABLE is never set here), and
honors the override when config_overlay.get() returns one. These are the
only new behaviors added by vendoring config_overlay.py - everything else
in src/knowledge.py, src/workdays.py and src/sla.py is unchanged.
"""
from datetime import date
from unittest.mock import patch

from src import knowledge, sla, workdays


def test_knowledge_load_falls_back_to_files_when_no_override():
    with patch("src.knowledge.config_overlay.get", return_value=None):
        assert knowledge.load() == knowledge._load_from_files()


def test_knowledge_load_uses_the_override_when_set():
    with patch("src.knowledge.config_overlay.get", return_value="# Override\n\nNew content."):
        assert knowledge.load() == "# Override\n\nNew content."


def test_holiday_override_replaces_the_bundled_list():
    # 2026-08-15 is a bundled holiday; the override below omits it but adds
    # a date that isn't bundled, so this only passes if the override - not
    # the bundled HOLIDAYS - is what's actually being read.
    with patch("src.workdays.config_overlay.get", return_value='["2099-01-01"]'):
        assert workdays.is_working_day(date(2026, 8, 15)) is True
        assert workdays.is_working_day(date(2099, 1, 1)) is False


def test_holiday_override_falls_back_to_bundled_list_when_unset():
    with patch("src.workdays.config_overlay.get", return_value=None):
        assert workdays.is_working_day(date(2026, 8, 15)) is False


def test_holiday_override_ignores_malformed_json():
    with patch("src.workdays.config_overlay.get", return_value="not json"):
        assert workdays.is_working_day(date(2026, 8, 15)) is False


def test_sla_override_changes_the_nudge_and_deadline_schedule():
    with patch("src.sla.config_overlay.get",
              return_value='{"sla_working_days": 5, "max_admin_nudges": 1, "student_reminders": 0}'):
        assert sla._sla_working_days() == 5
        assert sla._max_admin_nudges() == 1
        assert sla._student_reminders() == 0


def test_sla_override_falls_back_to_bundled_constants_when_unset():
    with patch("src.sla.config_overlay.get", return_value=None):
        assert sla._sla_working_days() == sla.SLA_WORKING_DAYS
        assert sla._max_admin_nudges() == sla.MAX_ADMIN_NUDGES
        assert sla._student_reminders() == sla.STUDENT_REMINDERS


def test_sla_override_partial_object_only_changes_the_fields_present():
    with patch("src.sla.config_overlay.get", return_value='{"max_admin_nudges": 4}'):
        assert sla._sla_working_days() == sla.SLA_WORKING_DAYS
        assert sla._max_admin_nudges() == 4
        assert sla._student_reminders() == sla.STUDENT_REMINDERS
