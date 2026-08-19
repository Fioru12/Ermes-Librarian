# =========================================================================
# TEST DI IMPORT PER MODULI UI STREAMLIT LEGACY (WinSarp)
# =========================================================================
# Spostato da tests/test_integration.py durante l'isolamento di WinSarp
# (docs/ROADMAP_V2.md, Fase A) — la UI React e' l'unica UI del prodotto.

class TestUntouchedModules:
    """Verifica che moduli non testati importino senza errori."""

    def test_admin_ui_imports(self):
        from legacy_winsarp.ui.admin_ui import render_admin_auth_section, render_user_management_section
        assert callable(render_admin_auth_section)
        assert callable(render_user_management_section)

    def test_monitor_dashboard_imports(self):
        from legacy_winsarp.ui.monitor_dashboard import (
            analyze_performance,
            count_queries,
            count_sessions,
            get_feedback_stats,
        )
        assert callable(count_sessions)
        assert callable(count_queries)
        assert callable(analyze_performance)
        assert callable(get_feedback_stats)

    def test_sidebar_ui_functions(self):
        from legacy_winsarp.ui.sidebar_ui import (
            render_logo,
            render_theme_toggle,
        )
        assert callable(render_logo)
        assert callable(render_theme_toggle)

    def test_welcome_ui_functions(self):
        from legacy_winsarp.ui.welcome_ui import (
            MODE_INFO,
        )
        assert "retrieval" in MODE_INFO
        assert "generazione" in MODE_INFO

    def test_chat_ui_functions(self):
        from legacy_winsarp.ui.chat_ui import (
            render_confidence_badge,
            render_history_messages,
            render_sources_block,
        )
        assert callable(render_history_messages)
        assert callable(render_sources_block)
        assert callable(render_confidence_badge)
