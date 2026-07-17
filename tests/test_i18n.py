from modules.ui.i18n import TRANSLATIONS, Translator, normalize_language


def test_english_is_default_and_unknown_languages_fall_back_to_english():
    assert normalize_language(None) == "en"
    assert normalize_language("fr_FR") == "en"
    assert Translator().text("button.daq.start") == "Start DAQ"


def test_simplified_chinese_can_be_selected_and_formatted():
    translator = Translator("zh-CN")

    assert translator.language == "zh_CN"
    assert translator("button.daq.start") == "开始采集"
    assert translator("force.total", value=1.25) == "合力: 1.25 N"
    assert translator("plot.total_force") == "合力"


def test_scan_workflow_messages_exist_in_every_supported_language():
    required = {
        "button.scan.preparing",
        "button.scan.running",
        "button.scan.saving",
        "scan.channels_required",
        "scan.load_confirmation_required",
        "scan.progress",
        "scan.saved_summary",
        "scan.saved_incomplete_summary",
        "scan.save_failed",
        "scan.saving_elapsed",
        "tab.results",
        "results.completed",
        "results.coverage",
        "settings.output_dir",
        "device.capabilities",
        "device.channel_unavailable",
        "device.rate_limit",
        "device.ao_range",
    }

    for catalog in TRANSLATIONS.values():
        assert required <= catalog.keys()
