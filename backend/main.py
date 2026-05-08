from dotenv import load_dotenv
from app.services.browser import BrowserService
from app.services.mailer import MailerService
from browser_use.llm import ChatOpenAI
import os 
import asyncio

load_dotenv()   


mailer = MailerService(email=os.getenv("MAILER_EMAIL", ""), password=os.getenv("MAILER_PASSWORD", ""), imap_server=os.getenv("MAILER_IMAP_SERVER", ""))
mailer.start()
