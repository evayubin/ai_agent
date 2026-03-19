import os
from dotenv import load_dotenv
load_dotenv()

from notion_client import Client
c = Client(auth=os.environ["NOTION_API_KEY"])
