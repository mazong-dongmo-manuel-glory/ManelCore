from imap_tools import MailBox, AND
class MailerService:
    def __init__(self, email : str, password : str, imap_server : str):
        self.email = email
        self.password = password
        self.imap_server = imap_server


    
    def start(self):

        try:
            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                print("Mailer service started, monitoring for new emails...")

                while True: 
                    response = mailbox.idle.wait(timeout=60)
                    if response:
                        for msg in mailbox.fetch(AND(seen=False)):
                            print(f"New email from: {msg.from_}, subject: {msg.subject}")

    
        except Exception as e:
            print(f"Error starting mailer service: {e}")
