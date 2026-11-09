"""Draw web snapshots at native resolution while retaining the device layout."""

from pathlib import Path

from PIL import ImageDraw

FONT_ROOT = Path(__file__).parent / "fonts/ProximaNova"
WEB_FONT = FONT_ROOT / "ProximaNovaRegular/ProximaNovaRegular.ttf"
WEB_BOLD_FONT = FONT_ROOT / "ProximaNovaBold/ProximaNovaBold.ttf"


class ScaledDraw:
    """Use logical layout coordinates with full-resolution shapes and font glyphs."""

    def __init__(self, image, scale):
        self.draw = ImageDraw.Draw(image)
        self.scale = scale
        self.fonts = {}

    def text(self, xy, text, *, font, **kwargs):
        self.draw.text(self._coords(xy), text, font=self._font(font), **kwargs)

    def textlength(self, text, *, font):
        return self.draw.textlength(text, font=self._font(font)) / self.scale

    def textbbox(self, xy, text, *, font, **kwargs):
        return tuple(
            value / self.scale
            for value in self.draw.textbbox(
                self._coords(xy), text, font=self._font(font), **kwargs
            )
        )

    def line(self, xy, *, width=1, **kwargs):
        self.draw.line(self._coords(xy), width=width * self.scale, **kwargs)

    def rectangle(self, xy, *, width=1, **kwargs):
        self.draw.rectangle(self._coords(xy), width=width * self.scale, **kwargs)

    def rounded_rectangle(self, xy, *, radius=0, width=1, **kwargs):
        self.draw.rounded_rectangle(
            self._coords(xy),
            radius=radius * self.scale,
            width=width * self.scale,
            **kwargs,
        )

    def ellipse(self, xy, *, width=1, **kwargs):
        self.draw.ellipse(self._coords(xy), width=width * self.scale, **kwargs)

    def _coords(self, values):
        return tuple(
            (
                self._coords(value)
                if isinstance(value, (tuple, list))
                else value * self.scale
            )
            for value in values
        )

    def _font(self, font):
        key = (font.path, font.size)
        if key not in self.fonts:
            self.fonts[key] = font.font_variant(size=font.size * self.scale)
        return self.fonts[key]
