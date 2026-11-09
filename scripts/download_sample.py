"""Download the public ASF Hawaii Sentinel-1 VV example without an account."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sar_viewer import download_sample

if __name__ == "__main__":
    print("Downloading / checking the ASF Hawaii sample (59 MB)…")
    print(download_sample())
