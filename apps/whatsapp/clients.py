from django.conf import settings

class WhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str, version: str = None):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.version = version or settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.version}/{phone_number_id}"

    def send_text_message(self, to: str, body: str):
        if settings.DEBUG:
            print("=== WHATSAPP MOCK ===")
            print(f"To: {to}")
            print(f"Message: {body}")
            print("====================")
            return {"status": "mocked"}

        import requests

        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
