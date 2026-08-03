import urllib.request
from pathlib import Path

from tqdm import tqdm


_FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)


def ensure_models(model_path: str) -> None:
    path = Path(model_path)
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nMediaPipe model not found at '{model_path}'.")
    print("Downloading face_landmarker.task (~2.5 MB)...\n")

    with tqdm(unit="B", unit_scale=True, unit_divisor=1024, miniters=1, desc="face_landmarker.task") as bar:
        def _progress(count: int, block_size: int, total_size: int) -> None:
            if bar.total is None and total_size > 0:
                bar.total = total_size
            bar.update(block_size)

        urllib.request.urlretrieve(_FACE_LANDMARKER_URL, path, _progress)

    print("\nDownload complete.\n")
