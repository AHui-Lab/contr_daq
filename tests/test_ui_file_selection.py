from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def test_main_loads_optimized_ui_without_removing_original_ui():
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert 'ORIGINAL_UI_FILE = BASE_DIR / "test.ui"' in main_source
    assert 'UI_FILE = BASE_DIR / "test_optimized.ui"' in main_source
    assert (ROOT / "test.ui").exists()
    assert (ROOT / "test_optimized.ui").exists()


def test_optimized_ui_gives_plot_regions_room_to_expand():
    tree = ET.parse(ROOT / "test_optimized.ui")
    root = tree.getroot()

    main_layout = root.find(".//layout[@name='gridLayout_3']")
    acquisition_layout = root.find(".//layout[@name='verticalLayout_2']")
    daq_plot = root.find(".//widget[@name='daqPlotWidget']")
    force_plot = root.find(".//widget[@name='forcePlotWidget']")

    assert main_layout.attrib["columnstretch"] == "4,4,2"
    assert main_layout.attrib["rowstretch"] == "5,3,1"
    assert acquisition_layout.attrib["stretch"] == "0,0,6,0,6,0"
    assert _maximum_width(daq_plot) == 16777215
    assert _maximum_width(force_plot) == 16777215
    assert _minimum_height(daq_plot) >= 240
    assert _minimum_height(force_plot) >= 220


def _maximum_width(widget):
    return int(widget.find("./property[@name='maximumSize']/size/width").text)


def _minimum_height(widget):
    return int(widget.find("./property[@name='minimumSize']/size/height").text)
