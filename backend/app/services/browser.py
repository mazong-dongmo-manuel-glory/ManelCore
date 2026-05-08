from browser_use import Agent
from browser_use.llm import ChatOpenAI
from .mailer import MailerService
class BrowserService:

    def __init__(self, api_key : str, llm : ChatOpenAI, task : dict):
        self.api_key = api_key
        self.llm = llm
        self.task = task
        self.agent = None 

    

    async def start(self, task : str):
        try:

            self.agent = Agent(api_key=self.api_key, llm=self.llm, task=self.task[task])
            await self.agent.run()
        except Exception as e:
            print(f"Error starting browser agent: {e}")



