from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEMO_USERS = ["alice", "bob"]
DEMO_PASSWORD = "demo-pass-123"


class Command(BaseCommand):
    help = f"Create demo users {', '.join(DEMO_USERS)} with password {DEMO_PASSWORD!r}."

    def handle(self, *args, **options):
        User = get_user_model()
        for username in DEMO_USERS:
            user, created = User.objects.get_or_create(username=username)
            user.set_password(DEMO_PASSWORD)
            user.save()
            action = "Created" if created else "Reset password for"
            self.stdout.write(f"{action} {username!r} (password: {DEMO_PASSWORD})")
