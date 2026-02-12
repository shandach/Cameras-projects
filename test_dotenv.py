
from dotenv import load_dotenv
import os

load_dotenv(".env.test", override=True)
print(f"VAR1: {os.getenv('VAR1')}")
print(f"VAR2: {os.getenv('VAR2')}")
