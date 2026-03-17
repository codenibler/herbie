from pathlib import Path
import shutil


TEMP_DIRS = (
    Path("voice_responses_temp"),
    Path("user_input_temp"),
)


def wipe_temp_dirs() -> None:
    for temp_dir in TEMP_DIRS:
        temp_dir.mkdir(parents=True, exist_ok=True)
        for child in temp_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()


if __name__ == "__main__":
    wipe_temp_dirs()
