"""Display profiles and named palettes stored in Gerty preferences."""

from typing import TypedDict


class DisplayProfileSettings(TypedDict):
    label: str
    width: int
    height: int
    mode: str


DISPLAY_PROFILES: dict[str, DisplayProfileSettings] = {
    "epaper_800x480": {
        "label": "Epaper 800 x 480 (Seeed TRMNL 7.5 inch OG DIY Kit)",
        "width": 800,
        "height": 480,
        "mode": "L",
    },
    "colour_240x240": {
        "label": "Colour 240 x 240 (ESP32-C6 1.3 inch LCD)",
        "width": 240,
        "height": 240,
        "mode": "RGB",
    },
    "colour_480x272": {
        "label": "Colour 480 x 272 (Guition JC4827W543)",
        "width": 480,
        "height": 272,
        "mode": "RGB",
    },
    "epaper_960x540": {
        "label": "Epaper 960 x 540 (LilyGO T5-ePaper-S3)",
        "width": 960,
        "height": 540,
        "mode": "L",
    },
    "colour_480x320": {
        "label": "Colour 480 x 320 (Guition JC3248W535)",
        "width": 480,
        "height": 320,
        "mode": "RGB",
    },
}

COLOUR_THEMES = {
    "Arctic": {
        "background": "#F4F8FC",
        "surface": "#FFFFFF",
        "text": "#172B3A",
        "muted": "#607789",
        "accent": "#1677C8",
        "secondary": "#5B6FD6",
        "border": "#C9D8E5",
        "positive": "#16845B",
        "negative": "#D83B52",
    },
    "Bright day": {
        "background": "#EAF1F7",
        "surface": "#FFFFFF",
        "text": "#14283D",
        "muted": "#486278",
        "accent": "#005DA8",
        "secondary": "#7951AA",
        "border": "#A8BECE",
        "positive": "#087746",
        "negative": "#BE2639",
    },
    "Cypherpunk": {
        "background": "#060A07",
        "surface": "#0D1510",
        "text": "#33FF66",
        "muted": "#75C78C",
        "accent": "#33FF66",
        "secondary": "#9AFFB3",
        "border": "#24452E",
        "positive": "#33FF66",
        "negative": "#FF718C",
    },
    "Forest": {
        "background": "#08120D",
        "surface": "#102019",
        "text": "#E4F4E8",
        "muted": "#88AA93",
        "accent": "#4FD18B",
        "secondary": "#A5D6A7",
        "border": "#294A36",
        "positive": "#4FD18B",
        "negative": "#F27777",
    },
    "Midnight": {
        "background": "#090B14",
        "surface": "#121625",
        "text": "#E8ECFF",
        "muted": "#8992B3",
        "accent": "#7C8CFF",
        "secondary": "#B58CFF",
        "border": "#29304A",
        "positive": "#5FE0A0",
        "negative": "#FF6B81",
    },
    "Mint Day": {
        "background": "#EEF8F4",
        "surface": "#FFFFFF",
        "text": "#17352C",
        "muted": "#5F7D72",
        "accent": "#168A68",
        "secondary": "#6474C5",
        "border": "#C4DED4",
        "positive": "#168A68",
        "negative": "#D64F5F",
    },
    "Orange Pill": {
        "background": "#15120F",
        "surface": "#29221A",
        "text": "#FFF4E5",
        "muted": "#C8B9A3",
        "accent": "#FF9C31",
        "secondary": "#FFD18A",
        "border": "#63503A",
        "positive": "#9DDD89",
        "negative": "#FF8174",
    },
    "Paper": {
        "background": "#F7F5F0",
        "surface": "#FFFFFF",
        "text": "#292722",
        "muted": "#756F64",
        "accent": "#A05A2C",
        "secondary": "#6B5B95",
        "border": "#D8D2C7",
        "positive": "#3D8054",
        "negative": "#C94A4A",
    },
    "Sunset": {
        "background": "#180F16",
        "surface": "#2A1822",
        "text": "#FFF0E8",
        "muted": "#C7A5A0",
        "accent": "#FF6F61",
        "secondary": "#FFB26B",
        "border": "#5A3036",
        "positive": "#8ED081",
        "negative": "#FF5C7A",
    },
}


def get_display_settings(preferences):
    display = preferences.get("_display", {})
    if not isinstance(display, dict):
        raise ValueError("Display preferences must be an object.")
    profile = display.get("profile", "epaper_960x540")
    theme = display.get("theme", "Orange Pill")
    if not isinstance(profile, str) or profile not in DISPLAY_PROFILES:
        raise ValueError("Unknown display profile.")
    if not isinstance(theme, str) or theme not in COLOUR_THEMES:
        raise ValueError("Unknown colour theme.")
    return profile, theme
