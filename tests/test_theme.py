from modules.ui.theme import (
    INDUSTRIAL_GRAPH_CONFIG,
    CAMERA_PREVIEW_STYLE,
    LED_OFF_STYLE,
    LED_ON_STYLE,
    STATUS_PILL_STYLE,
    build_stylesheet,
)


def test_build_stylesheet_contains_workbench_sections():
    stylesheet = build_stylesheet()

    assert "QMainWindow" in stylesheet
    assert "QGroupBox" in stylesheet
    assert "QGroupBox#groupBox_2" in stylesheet
    assert "QTabWidget#tabWidget_4 QPushButton" in stylesheet
    assert "QPushButton#Emergency_Stop" in stylesheet
    assert "QPushButton#Forward_circle:disabled" in stylesheet
    assert "QGroupBox#groupBox_6 QPushButton#Emergency_Stop" in stylesheet
    assert "QFrame#scanResultsMetrics" in stylesheet
    assert "QLabel#scanResultQuality" in stylesheet
    assert "QPlainTextEdit" in stylesheet


def test_led_styles_are_distinct_status_tokens():
    assert "#2eea78" in LED_ON_STYLE
    assert "#26313a" in LED_OFF_STYLE
    assert LED_ON_STYLE != LED_OFF_STYLE


def test_graph_config_uses_dark_workbench_palette():
    assert INDUSTRIAL_GRAPH_CONFIG["background"] == "#0b0f14"
    assert INDUSTRIAL_GRAPH_CONFIG["foreground"] == "#d8e1ea"
    assert INDUSTRIAL_GRAPH_CONFIG["antialias"] is True


def test_status_pill_style_is_available_for_runtime_labels():
    assert "#17242d" in STATUS_PILL_STYLE
    assert "border-radius" in STATUS_PILL_STYLE


def test_camera_preview_style_uses_framed_dark_surface():
    assert "#050708" in CAMERA_PREVIEW_STYLE
    assert "border" in CAMERA_PREVIEW_STYLE


def test_apply_graph_theme_skips_options_missing_in_old_pyqtgraph():
    from modules.ui.theme import apply_graph_theme

    class FakePyQtGraph:
        def __init__(self):
            self.options = {}
            self.kwargs = {}

        def setConfigOption(self, key, value):
            if key == "gridColor":
                raise KeyError(key)
            self.options[key] = value

        def setConfigOptions(self, **kwargs):
            self.kwargs.update(kwargs)

    fake_pg = FakePyQtGraph()

    apply_graph_theme(fake_pg)

    assert fake_pg.options == {
        "background": "#0b0f14",
        "foreground": "#d8e1ea",
    }
    assert fake_pg.kwargs == {"antialias": True}
