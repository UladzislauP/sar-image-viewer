"""Run with: python -m streamlit run app.py"""

import json
from pathlib import Path

import numpy as np
import streamlit as st
from rasterio.errors import RasterioError

from sar_viewer import (
    PALETTES, SAMPLE_PATH, SAMPLE_URL, display_values, download_sample,
    png_bytes, read_preview, read_upload, render_image,
)

st.set_page_config(page_title="SAR Image Viewer", page_icon="🛰️", layout="wide")
st.markdown("""
<style>
.block-container {padding: 4.5rem 2rem 2rem; max-width: 1500px; min-width: 0;}
h1 {letter-spacing: -0.045em;}
[data-testid="stMetric"] {background: #191d27; border: 1px solid #2b3040;
 border-radius: 12px; padding: 14px 18px; height: 100%; box-sizing: border-box;}
.st-key-image_stats {container-type: inline-size;}
.st-key-image_stats [data-testid="stHorizontalBlock"] {flex-wrap: wrap; align-items: stretch;}
.st-key-image_stats [data-testid="stColumn"] {min-width: 0;}
.st-key-image_stats [data-testid="stMetricValue"] {font-size: 1.45rem; line-height: 1.4;}
.st-key-image_stats [data-testid="stMetricValue"],
.st-key-image_stats [data-testid="stMetricValue"] *,
.st-key-image_stats [data-testid="stMetricLabel"],
.st-key-image_stats [data-testid="stMetricLabel"] * {
 white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere;}
@container (max-width: 1050px) {
 .st-key-image_stats [data-testid="stColumn"] {
  flex: 1 1 calc(50% - 1rem); width: calc(50% - 1rem);}
}
@container (max-width: 450px) {
 .st-key-image_stats [data-testid="stColumn"] {flex-basis: 100%; width: 100%;}
}
@media (max-width: 640px) {
 .block-container {padding-right: 1rem; padding-left: 1rem;}
}
.eyebrow {color: #a9e4cb; font-size: .78rem; letter-spacing: .18em; font-weight: 600;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(max_entries=3, show_spinner=False)
def load_local(path, modified, band):
    return read_preview(path, band)


@st.cache_data(max_entries=2, show_spinner=False)
def load_upload(content, band):
    return read_upload(content, band)


with st.sidebar:
    st.markdown("### 🛰️ SAR Image Viewer")
    st.caption("Исследуйте радарные снимки")
    st.divider()
    source = st.radio("Источник", ["Пример · Гавайи", "Мой GeoTIFF"])
    uploaded = None
    if source == "Мой GeoTIFF":
        uploaded = st.file_uploader("Открыть снимок", type=["tif", "tiff"])
        st.caption("До 200 МБ. Подготовленный RTC или GRD GeoTIFF.")
    else:
        st.caption("Sentinel-1B · VV · 9 октября 2020\n\nASF / Copernicus · RTC · 30 м")
        if not SAMPLE_PATH.exists():
            if st.button("Скачать пример · 59 МБ", type="primary", width="stretch"):
                try:
                    with st.spinner("Скачивание снимка ASF…"):
                        download_sample()
                    st.rerun()
                except (OSError, ValueError, RasterioError) as error:
                    st.error(f"Не удалось скачать снимок: {error}")
        st.link_button("Источник снимка ↗", SAMPLE_URL, width="stretch")

st.markdown('<div class="eyebrow">RADAR IMAGERY / EXPLORER</div>', unsafe_allow_html=True)
st.title("Увидеть больше в SAR")
st.caption("Откройте GeoTIFF, настройте изображение и сохраните свой результат.")

if source == "Мой GeoTIFF" and uploaded is None:
    st.info("Загрузите .tif или .tiff на боковой панели. Для первого знакомства выберите пример Гавайев.")
    st.stop()
if source == "Пример · Гавайи" and not SAMPLE_PATH.exists():
    st.info("Нажмите «Скачать пример» слева — приложение загрузит настоящий SAR-снимок без регистрации.")
    st.stop()

try:
    with st.spinner("Чтение GeoTIFF…"):
        if uploaded is not None:
            content = uploaded.getvalue()
            loader = lambda band: load_upload(content, band)
            name = uploaded.name
        else:
            loader = lambda band: load_local(str(SAMPLE_PATH), SAMPLE_PATH.stat().st_mtime_ns, band)
            name = SAMPLE_PATH.name
        data, info = loader(1)
        with st.sidebar:
            band = st.selectbox("Канал", list(range(1, info["bands"] + 1)))
        if band != 1:
            data, info = loader(band)
except (RasterioError, ValueError, OSError) as error:
    st.error(f"Не удалось открыть GeoTIFF: {error}")
    st.stop()

with st.sidebar:
    st.divider()
    st.markdown("#### Отображение")
    scales = {"Как в файле": "native", "Мощность → dB (10 log₁₀)": "power",
              "Амплитуда → dB (20 log₁₀)": "amplitude"}
    scale_label = st.selectbox("Шкала", list(scales), index=1 if uploaded is None else 0)
    st.caption("Если данные уже в dB, выберите «Как в файле».")
    palette = st.selectbox("Палитра", list(PALETTES))
    percentiles = st.slider("Процентильное растяжение", 0, 100, (2, 98))
    brightness = st.slider("Яркость", -0.5, 0.5, 0.0, 0.05)
    contrast = st.slider("Контраст", 0.2, 3.0, 1.0, 0.1)
    gamma = st.slider("Гамма", 0.2, 3.0, 1.0, 0.1)

if percentiles[0] >= percentiles[1]:
    st.warning("Левая граница процентилей должна быть меньше правой.")
    st.stop()
values = display_values(data, scales[scale_label])
try:
    original = render_image(values)
    processed = render_image(values, percentiles, brightness, contrast, gamma, palette)
except ValueError as error:
    st.warning(str(error))
    st.stop()

with st.container(key="image_stats"):
    a, b, c, d = st.columns(4)
    a.metric("Размер исходника", f'{info["width"]:,} × {info["height"]:,}')
    b.metric("Каналы", str(info["bands"]))
    c.metric("Система координат", info["crs"])
    d.metric("Валидные пиксели превью", f"{np.isfinite(values).mean():.1%}")
st.write("")
compare, details = st.tabs(["Сравнение", "О снимке"])
with compare:
    left, right = st.columns(2)
    with left:
        st.markdown("#### Базовое изображение")
        st.caption("Выбранная шкала · Grayscale · процентили 2–98")
        st.image(original, width="stretch")
    with right:
        st.markdown("#### Ваша обработка")
        st.caption(f"{scale_label} · {palette} · процентили {percentiles[0]}–{percentiles[1]}")
        st.image(processed, width="stretch")
    st.caption(f'Превью: {info["preview_width"]} × {info["preview_height"]} px. '
               "Прозрачные участки — NoData или значения, непригодные для выбранной шкалы.")
    settings = {"source": name, "band": band, "scale": scales[scale_label],
                "percentiles": percentiles, "brightness": brightness, "contrast": contrast,
                "gamma": gamma, "palette": palette, "preview_size": list(processed.size)}
    export, recipe = st.columns(2)
    export.download_button("↓ Скачать PNG", png_bytes(processed),
                           file_name=f"{Path(name).stem}_preview.png", mime="image/png",
                           type="primary", width="stretch")
    recipe.download_button("↓ Скачать настройки JSON", json.dumps(settings, ensure_ascii=False, indent=2),
                           file_name="sar_display_settings.json", mime="application/json",
                           width="stretch")
    st.caption("PNG сохраняется в разрешении превью, без геопривязки. Исходный GeoTIFF не изменяется.")
with details:
    st.write(f"**Файл:** {name}")
    st.json(info)
    st.markdown("**Что показывает SAR?** Яркость отражает силу обратного радарного рассеяния. "
                "Палитры — условные цвета, а не естественная окраска поверхности.")
    st.markdown("Просмотрщик не выполняет калибровку или коррекцию рельефа. "
                "Для научного анализа используйте подготовленные данные и учитывайте метаданные продукта.")
    if uploaded is None:
        st.markdown("Содержит модифицированные данные Copernicus Sentinel (2020), обработанные ASF DAAC / HyP3. "
                    "Изменения здесь относятся только к отображению. "
                    "[Описание RTC](https://hyp3-docs.asf.alaska.edu/guides/rtc_product_guide/)")
