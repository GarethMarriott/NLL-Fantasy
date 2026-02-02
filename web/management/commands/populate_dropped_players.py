from django.core.management.base import BaseCommand
from web.models import ChatMessage, Player
import re


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
            if msg.team is None:
                continue
                
            # Check if message mentions "dropped"
            if 'dropped' in msg.message.lower():
                # Extract the dropped player name using regex
                # Message format: "⚡ WAIVER: Team claimed AddedPlayer, dropped DroppedPlayer"
                match = re.search(r'dropped\s+(\w+)(?:\s+(\w+))?', msg.message, re.IGNORECASE)
                
                if match:
                    first_name = match.group(1)
                    last_name = match.group(2) if match.group(2) else ''
                    
                    try:
                        # Try to find the player
                        if last_name:
                            player = Player.objects.filter(
                                first_name__iexact=first_name,
                                last_name__iexact=last_name
                            ).first()
                        else:
                            # Single name, try to find by first name or look for last name
                            player = Player.objects.filter(
                                last_name__iexact=first_name
                            ).first()
                            if not player:
                                player = Player.objects.filter(
                                    first_name__iexact=first_name
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
                                    f"  ✗ {msg.team.name}: Could not find player: {first_name} {last_name}"
                                )
                            )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  Error processing message: {str(e)}")
                        )
        
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal updated: {updated} messages")
        )
