from django.core.management.base import BaseCommand
from web.models import ChatMessage, Player


class Command(BaseCommand):
    help = 'Populate player_dropped field for existing ADD messages'

    def handle(self, *args, **options):
        # Find all ADD messages that have no player_dropped but mention a dropped player
        add_messages = ChatMessage.objects.filter(
            message_type=ChatMessage.MessageType.ADD,
            player_dropped__isnull=True
        )
        
        updated = 0
        for msg in add_messages:
            # Check if message mentions "dropped"
            if 'dropped' in msg.message.lower():
                # Extract the dropped player name
                # Message format: "⚡ WAIVER: Team claimed AddedPlayer, dropped DroppedPlayer"
                if ', dropped ' in msg.message:
                    dropped_name = msg.message.split(', dropped ')[-1].strip()
                    
                    # Try to find the player
                    try:
                        # Split into first and last name
                        parts = dropped_name.split()
                        if len(parts) >= 2:
                            last_name = ' '.join(parts[1:])  # Handle multi-word last names
                            first_name = parts[0]
                            
                            player = Player.objects.filter(
                                first_name__iexact=first_name,
                                last_name__iexact=last_name
                            ).first()
                            
                            if player:
                                msg.player_dropped = player
                                msg.save()
                                updated += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"✓ {msg.team.name}: Set dropped player to {player.first_name} {player.last_name}"
                                    )
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"  ✗ Could not find player: {first_name} {last_name}"
                                    )
                                )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  Error processing message: {str(e)}")
                        )
        
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal updated: {updated} messages")
        )
