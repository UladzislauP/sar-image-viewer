"""Bounded GeoTIFF previews and display-only SAR transformations."""

from io import BytesIO
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "data" / "hawaii_sentinel1_vv.tif"
PRODUCT = "S1B_IW_20201009T161543_DVR_RTC30_G_gpuned_27D0"
SAMPLE_URL = (
    "https://hyp3-examples.s3.us-west-2.amazonaws.com/RTC_GAMMA/Hawaii/"
    f"{PRODUCT}/{PRODUCT}_VV.tif"
)
SAMPLE_BYTES = 59_098_760
PALETTES = {
    "Grayscale": ["#000000", "#ffffff"],
    "Ocean": ["#061526", "#164b71", "#26a5ab", "#b3f1d0", "#ffffff"],
    "Amber": ["#100e19", "#542349", "#b64a45", "#f5ad55", "#fff3cd"],
    "Violet": ["#0b1024", "#41448c", "#9b80d2", "#ead8ef", "#ffffff"],
}


def read_preview(source, band=1, max_side=1600):
    """Read at most max_side² pixels; keep the source NoData mask."""
    with rasterio.open(source) as src:
        if not 1 <= band <= src.count:
            raise ValueError("Указанный канал отсутствует в файле.")
        if np.dtype(src.dtypes[band - 1]).kind == "c":
            raise ValueError("Комплексные SLC-данные не поддерживаются. Выберите RTC/GRD GeoTIFF.")
        ratio = min(1.0, max_side / max(src.width, src.height))
        shape = (max(1, round(src.height * ratio)), max(1, round(src.width * ratio)))
        data = src.read(band, out_shape=shape, masked=True, resampling=Resampling.nearest)
        array = data.astype(np.float32).filled(np.nan)
        array[~np.isfinite(array)] = np.nan
        info = {
            "width": src.width, "height": src.height, "bands": src.count,
            "dtype": src.dtypes[band - 1],
            "crs": str(src.crs) if src.crs else "Не задана",
            "resolution": list(src.res), "bounds": list(src.bounds),
            "nodata": str(src.nodata), "preview_width": shape[1],
            "preview_height": shape[0], "tags": src.tags(),
        }
    return array, info


def read_upload(content, band=1):
    with MemoryFile(content) as memory:
        return read_preview(memory.name, band)


def display_values(array, scale):
    """Convert calibrated linear power/amplitude only when explicitly selected."""
    values = np.array(array, dtype=np.float32, copy=True)
    values[~np.isfinite(values)] = np.nan
    if scale in ("power", "amplitude"):
        values[values <= 0] = np.nan
        factor = 10 if scale == "power" else 20
        with np.errstate(invalid="ignore", divide="ignore"):
            values = factor * np.log10(values)
    elif scale != "native":
        raise ValueError("Unknown scale")
    return values


def render_image(values, percentiles=(2, 98), brightness=0.0, contrast=1.0,
                 gamma=1.0, palette="Grayscale"):
    """Return RGBA image; invalid pixels stay transparent through all adjustments."""
    valid = np.isfinite(values)
    if not valid.any():
        raise ValueError("Нет пригодных пикселей. Проверьте канал и выбранную шкалу.")
    low, high = np.percentile(values[valid], percentiles)
    normalized = np.zeros(values.shape, dtype=np.float32)
    if high > low:
        normalized[valid] = np.clip((values[valid] - low) / (high - low), 0, 1)
    else:
        normalized[valid] = 0.5
    normalized = np.clip((normalized - 0.5) * contrast + 0.5 + brightness, 0, 1)
    normalized = normalized ** (1.0 / gamma)
    colors = np.array([
        [int(color[i:i + 2], 16) for i in (1, 3, 5)] for color in PALETTES[palette]
    ])
    stops = np.linspace(0, 1, len(colors))
    rgb = np.stack([np.interp(normalized, stops, colors[:, i]) for i in range(3)], axis=-1)
    rgba = np.concatenate([rgb.astype(np.uint8), (valid * 255).astype(np.uint8)[..., None]], axis=-1)
    return Image.fromarray(rgba)


def png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def download_sample():
    """Download one fixed public ASF asset, validate, then atomically publish it."""
    if SAMPLE_PATH.exists():
        read_preview(SAMPLE_PATH, max_side=64)
        return SAMPLE_PATH
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SAMPLE_PATH.with_suffix(".part")
    try:
        request = urllib.request.Request(SAMPLE_URL, headers={"User-Agent": "sar-image-viewer/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise ValueError("Размер примера превышает допустимый предел.")
                output.write(chunk)
        if total != SAMPLE_BYTES:
            raise ValueError("Размер снимка отличается от ожидаемого. Загрузка не завершена или источник изменился.")
        read_preview(temporary, max_side=64)
        temporary.replace(SAMPLE_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    return SAMPLE_PATH
