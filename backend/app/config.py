import os
from pydantic_settings import BaseSettings
from pathlib import Path
from loguru import logger
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    JANASUNANI_API_BASE_URL: str = os.getenv(
        "JANASUNANI_API_BASE_URL", "https://janasunani.odisha.gov.in/api/DataServices"
    )
    JANASUNANI_API_USERNAME: str = os.getenv("JANASUNANI_API_USERNAME")
    JANASUNANI_API_PASSWORD: str = os.getenv("JANASUNANI_API_PASSWORD")
    DB_URL: str = os.getenv("DB_URL", "sqlite:///./grievance.db")

    class Config:
        env_file = ROOT_DIR / ".env"


settings = Settings()

def stop_logging_to_console(filename: str, mode: str = "a"):
    """
    Stops logging messages to the console and redirects them to a file.

    This function removes all existing logging handlers, effectively stopping
    any logging to the console. It then adds a new logging handler that writes
    log messages to the specified file. This is useful for capturing log
    messages in a file instead of displaying them in the console.

    Parameters
    ----------
    filename : str
        The path of the file where log messages should be written.
    mode : str, optional
        The mode in which the file is opened. Default is "a", which means
        append mode. Use "w" for write mode to overwrite the file.
    """
    for handler_id in list(logger._core.handlers.keys()):
        logger.remove(handler_id)

    # Add new logger
    logger.add(
        filename,
        format="{time} {level} {message}",
        level="INFO",
        colorize=True,
        catch=True,
        mode=mode,
    )

def resume_logging_to_console():
    """
    Resumes logging messages to the console using tqdm for writing.

    This function adds a new logging handler that writes log messages to the
    console. The messages are displayed using tqdm's write function, which is
    useful for keeping log messages separate from progress bar outputs.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    logger.add(lambda msg: tqdm.write(msg, end=""), colorize=True)

