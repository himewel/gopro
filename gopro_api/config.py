"""Environment-backed settings (e.g. ``GP_ACCESS_TOKEN`` from ``.env``)."""

import os
from dotenv import load_dotenv


load_dotenv()

GP_ACCESS_TOKEN = os.getenv("GP_ACCESS_TOKEN")
