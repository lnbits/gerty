# Gerty - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>

<small>For more about LNBits extension check [this tutorial](https://github.com/lnbits/lnbits/wiki/LNbits-Extensions)</small>

### Your Desktop Bitcoin Assistant

Gerty, a Bitcoin Assistant controlled from your LNbits wallet.

This extension can be used as a standalone to display a dashboard of Bitcoin information or you
can build / buy the Gerty hardware to display the information on an eink display.

Build your own Gerty or buy a [pre-assembled Gerty from the LNbits shop](https://shop.lnbits.com/product/gerty-a-bitcoin-assistant).

![Gerty](https://github.com/lnbits/gerty/raw/main/img/gerty-satoshi2.jpg)

[Find out more about the hardware Gerty here](https://github.com/lnbits/gerty/)

What does Gerty show?

- Current block height
- A list of Satoshi's quotes from bitcointalk.org
- Your LNbits wallet balance
- An onchain dashboard
- A lightning dashboard
- A mining dashboard
- Current Bitcoin price in your preferred currency
- Website status check

## Usage

- Create an LNbits wallet and enable the Gerty extension
- Create a new Gerty and configure your Gerty options
- Click the smiley face icon next to your Gerty to open your Gerty dashboard.

## Development

Use Python 3.12, uv, and Node.js to install the development dependencies:

```sh
uv sync --locked --all-extras --dev
npm ci
make check
make test
```

After changing Python dependencies in `pyproject.toml`, run `uv lock` and commit
the updated `uv.lock` alongside it.

## Image display API

Choose **Device type and screen resolution** in Gerty settings:

- **Epaper 960 x 540** (default): 16-level grayscale PNG.
- **Colour 480 x 320**: native RGB PNG layouts for the Guition JC3248W535.
- **Colour 240 x 240**: native RGB PNG layouts for the ESP32-C6 1.3 inch LCD, with a compact Block explorer layout.
- **Colour 480 x 272**: native RGB PNG layouts for the Guition JC4827W543.

Colour displays offer **Cypherpunk**, **Bright day**, and **Orange Pill**.
Their named colour-role dictionaries live in `display_settings.py`.
The selection is stored inside the existing JSON `display_preferences` field:

```json
{
  "onchain_block_height": true,
  "block_explorer": true,
  "_display": {
    "profile": "colour_480x320",
    "theme": "Orange Pill"
  }
}
```

The page API returns `device_type` (`epaper_960x540`, `colour_480x320`, `colour_480x272`, or `colour_240x240`),
`width`, `height`, and `colour_theme` (null for e-paper). Its `image_url` serves
the selected device's image. Display settings do not count as enabled pages.
Changing profile or theme invalidates the cached snapshot. Old preferences
without `_display` continue to use e-paper. No database migration is needed.

`GET /gerty/api/v1/gerty/pages/{id}` returns page zero. Append `/{page}`
for another zero-based enabled page. Requests outside the enabled page range
return the first enabled page, with its actual `page`, `screen_name`, and
`next_page`, so devices recover after screens are disabled. If no screens are
enabled, the API returns 422. The old text-area response is replaced by:

```json
{
  "schema_version": 1,
  "image_url": "https://your-lnbits/gerty/api/v1/gerty/images/REVISION.png",
  "image_revision": "REVISION",
  "refresh_seconds": 300,
  "page": 0,
  "page_count": 8,
  "next_page": 1
}
```

Download `image_url`, display the PNG, sleep for `refresh_seconds`, then request
`next_page`. On HTTP 410 from an image URL, fetch the manifest again. On data or
network errors, retain the current display and retry. URLs use the request's
origin: configure LNbits/proxy forwarding correctly and use a hostname the device
can reach (not localhost). Treat device URLs as private bearer links because
images may contain wallet balances.

E-paper images are 960 × 540 landscape, non-interlaced 8-bit grayscale PNGs quantized to
16 levels. The renderer uses Pixel Operator and Pixel Operator Bold from
`fonts/PixelOperator/`, with the bundled CC0 licence in `LICENSE.txt`.
The bottom-right timestamp is snapshot generation time in the configured UTC
offset, not confirmation of a physical panel update. No face or device name is
rendered. The browser display previews these same images.

Generated PNGs exist only in process memory: at most 32 MiB, with snapshots
expiring after 24 hours or earlier under memory pressure. Fresh snapshots are
reused for the refresh interval. Configuration changes invalidate reuse.
Restarting LNbits clears the cache. Run this extension in a single worker;
multiple workers would require a shared cache. No persistent image storage or
background rendering task is used.

The current overnight sleep behaviour is retained (eight hours for requests
between 22:00 and midnight in the configured offset). Firmware must honour that
interval and `next_page`. Positive configured intervals are returned without
a 30–300 second clamp; the updated gerty-v3 firmware honours them after reflashing.
For server-quantized images, disable
firmware dithering. Future display profiles can separate dimensions and palette
from the shared screen data. Both display profiles use the same live data sources.

The Block explorer toggle adds a live `block_explorer` page. It uses the same
LNbits services as `/blockexplorer/api/v1/tip`, `/fees`, and `/blocks`, without
making HTTP requests back to the server or forwarding credentials. Block explorer
must be enabled in LNbits settings. Its image shows confirmation-target fees,
recent blocks, block intervals, and mempool virtual size by fee-rate range.
Fee estimates are converted from BTC/kB to sat/vB; chart sizes use decimal MvB.
Unavailable fee estimates and missing interval history are shown explicitly.
The normal page cache and refresh interval apply; no static example data is used.
The standalone `GET /gerty/api/v1/gerty/block-explorer` also renders live data
and requires an LNbits invoice/read key. Hardware should use the Gerty page URL.

### Gallery

Enable **Gallery** in Gerty settings to upload JPEG or PNG photos. Each photo
becomes a page in the rotation, using the configured refresh time. Photos are center-cropped to fill the
selected display; e-paper displays use 16-level grayscale.

Uploads use LNbits account asset storage and its configured file size, type and
count limits (requires an LNbits version with `/api/v1/assets` support). Originals
remain private account assets, but rendered photos can be viewed by anyone with
the Gerty display link. Deleting a photo from Gallery immediately deletes its original from LNbits files.
Deleting a Gerty does not delete its uploaded files.
