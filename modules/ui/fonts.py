from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT_FILES = ("InterVariable.ttf", "NotoSansSC-VF.ttf")


def load_application_fonts(app) -> list[str]:
    families = []
    for filename in FONT_FILES:
        path = FONT_DIR / filename
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))

    primary = next((name for name in families if name.lower().startswith("inter")), None)
    if primary:
        app.setFont(QFont(primary, 10))
    return families
