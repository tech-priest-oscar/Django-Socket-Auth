from django_socket_auth.consumers import AuthenticatedJsonWebsocketConsumer

MAX_MESSAGE_LENGTH = 1000


class ChatConsumer(AuthenticatedJsonWebsocketConsumer):
    """
    A chat room. Everyone connected to the same room receives every message.

    AuthenticatedJsonWebsocketConsumer closes unauthenticated connections with
    code 4001 before authenticated_connect() is ever called, so everything
    below can rely on self.user being a real, logged-in user.
    """

    async def authenticated_connect(self):
        self.room = self.scope["url_route"]["kwargs"]["room"]
        self.group = f"chat_{self.room}"

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json(
            {"type": "welcome", "user": self.user.get_username(), "room": self.room}
        )

    async def disconnect(self, code):
        # Unauthenticated connections never joined a group.
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message = str(content.get("message", "")).strip()[:MAX_MESSAGE_LENGTH]
        if not message:
            return

        await self.channel_layer.group_send(
            self.group,
            {
                "type": "chat.message",  # calls chat_message() on every member
                "user": self.user.get_username(),
                "message": message,
            },
        )

    async def chat_message(self, event):
        await self.send_json(
            {"type": "message", "user": event["user"], "message": event["message"]}
        )
