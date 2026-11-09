from io import BytesIO
from pathlib import Path
import unittest

import numpy as np
from PIL import Image
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from sar_viewer import display_values, png_bytes, read_preview, read_upload, render_image


class RenderingTests(unittest.TestCase):
    def test_power_and_amplitude_decibels_and_invalid_pixels(self):
        source = np.array([[1, 10, 100, 0, -1, np.inf]], dtype=np.float32)
        power = display_values(source, "power")
        amplitude = display_values(source, "amplitude")
        np.testing.assert_allclose(power[0, :3], [0, 10, 20], atol=1e-5)
        np.testing.assert_allclose(amplitude[0, :3], [0, 20, 40], atol=1e-5)
        self.assertTrue(np.isnan(power[0, 3:]).all())
        self.assertEqual(source[0, 3], 0)

    def test_native_db_is_not_transformed(self):
        values = np.array([[-30, -10, 0, 5]], dtype=np.float32)
        np.testing.assert_array_equal(display_values(values, "native"), values)

    def test_nodata_stays_transparent_in_export(self):
        values = np.array([[np.nan, -10], [0, 10]], dtype=np.float32)
        result = render_image(values, brightness=0.5, palette="Ocean")
        exported = Image.open(BytesIO(png_bytes(result)))
        self.assertEqual(exported.mode, "RGBA")
        self.assertEqual(exported.getpixel((0, 0))[3], 0)
        self.assertEqual(exported.getpixel((1, 0))[3], 255)

    def test_empty_and_constant_images(self):
        with self.assertRaises(ValueError):
            render_image(np.full((3, 3), np.nan))
        self.assertEqual(render_image(np.ones((2, 2))).getpixel((0, 0)), (127, 127, 127, 255))

    def test_geotiff_upload_nodata_and_bounded_preview(self):
        values = np.ones((100, 200), dtype=np.float32)
        values[0, 0] = -9999
        with MemoryFile() as memory:
            with memory.open(driver="GTiff", height=100, width=200, count=1,
                             dtype="float32", nodata=-9999, crs="EPSG:32604",
                             transform=from_origin(100, 500, 30, 30)) as raster:
                raster.write(values, 1)
            content = memory.read()
            array, info = read_upload(content)
            self.assertTrue(np.isnan(array[0, 0]))
            self.assertEqual(info["crs"], "EPSG:32604")
            small, _ = read_preview(memory.name, max_side=50)
            self.assertEqual(small.shape, (25, 50))
        with self.assertRaises(rasterio.errors.RasterioError):
            read_upload(b"not a TIFF")


class ApplicationTests(unittest.TestCase):
    def test_real_sample_and_controls(self):
        from sar_viewer import SAMPLE_PATH
        from streamlit.testing.v1 import AppTest
        if not SAMPLE_PATH.exists():
            self.skipTest("Download sample for real-data app smoke test")
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 4)
        app.selectbox[2].select("Ocean")
        app.slider[1].set_value(0.2)
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        app.slider[0].set_value((50, 50)).run(timeout=30)
        self.assertEqual(len(app.warning), 1)
        self.assertEqual(len(app.exception), 0)
        app.radio[0].set_value("Мой GeoTIFF").run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.info), 1)


if __name__ == "__main__":
    unittest.main()
