from . import db
from .models import Setting
from .services.render import DEFAULT_STYLE

STYLE_KEY = "render_style"


def get_style() -> dict:
    with db.session() as s:
        row = s.get(Setting, STYLE_KEY)
        return {**DEFAULT_STYLE, **(row.value if row else {})}


def set_style(values: dict) -> dict:
    style = {**get_style(), **{k: v for k, v in values.items() if k in DEFAULT_STYLE}}
    with db.session() as s:
        row = s.get(Setting, STYLE_KEY) or Setting(key=STYLE_KEY)
        row.value = style
        s.add(row)
        s.commit()
    return style
