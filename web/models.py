from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
import secrets
import string
import pytz


class League(models.Model):
        # Multi-game week scoring method
    """Fantasy league that contains multiple teams"""
    ROSTER_FORMAT_CHOICES = [
        ("bestball", "Best Ball (no lineup management)"),
        ("traditional", "Traditional (starter slots: 3O, 3D, 1G)"),
    ]
    roster_format = models.CharField(
        max_length=15,
        choices=ROSTER_FORMAT_CHOICES,
        default="bestball",
        help_text="League format: Best Ball (all players score) or Traditional (only starters score)"
    )
    MULTIGAME_SCORING_CHOICES = [
        ("highest", "Use highest single-game score (default)"),
        ("average", "Use average of all games that week"),
    ]
    multigame_scoring = models.CharField(
        max_length=10,
        choices=MULTIGAME_SCORING_CHOICES,
        default="highest",
        help_text="If a player plays multiple games in a week, use their highest single-game score or the average of their games."
    )
    name = models.CharField(max_length=100)
    unique_id = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        help_text="Unique 8-character code for finding and joining the league"
    )
    commissioner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leagues_as_commissioner',
        help_text="User who created and manages the league"
    )
    description = models.TextField(blank=True)
    max_teams = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(2), MaxValueValidator(12)],
        help_text="Maximum number of teams allowed (must be even: 4, 6, 8, 10, or 12)"
    )
    is_active = models.BooleanField(default=True)
    
    # Commissioner Settings
    is_public = models.BooleanField(
        default=True,
        help_text="Whether the league is publicly visible and joinable"
    )
    roster_size = models.PositiveSmallIntegerField(
        default=14,
        validators=[MinValueValidator(6), MaxValueValidator(20)],
        help_text="Maximum number of players per team"
    )
    roster_forwards = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="Number of forward (O) roster spots"
    )
    roster_defense = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="Number of defense (D) roster spots"
    )
    roster_goalies = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="Number of goalie (G) roster spots"
    )
    roster_bench = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="Number of bench roster spots (for traditional leagues)"
    )
    playoff_weeks = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        help_text="Number of playoff weeks (0-4)"
    )
    playoff_teams = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(8)],
        help_text="Number of teams that make playoffs (2, 4, 6, or 8)"
    )
    
    use_waivers = models.BooleanField(
        default=False,
        help_text="Enable waiver claims that process when rosters unlock on Tuesday"
    )

    # League Type (Dynasty vs Re-Draft)
    LEAGUE_TYPE_CHOICES = [
        ("dynasty", "Dynasty (players stay on teams between seasons)"),
        ("redraft", "Re-Draft (all players removed when league renews)"),
    ]
    league_type = models.CharField(
        max_length=10,
        choices=LEAGUE_TYPE_CHOICES,
        default="redraft",
        help_text="Dynasty leagues preserve rosters when renewed; Re-Draft leagues clear all rosters"
    )
    
    # Taxi Squad Size (Dynasty leagues only)
    taxi_squad_size = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        help_text="Number of taxi squad slots for rookies (0-4, only used in Dynasty leagues)"
    )

    # Playoff reseed option for 6-team playoffs
    PLAYOFF_RESEED_CHOICES = [
        ("fixed", "1 seed plays winner of 3 vs 6"),
        ("reseed", "1 seed plays lowest remaining seed")
    ]
    playoff_reseed = models.CharField(
        max_length=10,
        choices=PLAYOFF_RESEED_CHOICES,
        default="fixed",
        help_text="Semifinal matchup: 1 seed plays winner of 3 vs 6 (fixed) or lowest remaining seed (reseed)"
    )
    
    # Custom Scoring Settings
    scoring_goals = models.DecimalField(
        max_digits=5, decimal_places=2, default=4.00,
        help_text="Points per goal"
    )
    scoring_assists = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.00,
        help_text="Points per assist"
    )
    scoring_loose_balls = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.00,
        help_text="Points per loose ball"
    )
    scoring_caused_turnovers = models.DecimalField(
        max_digits=5, decimal_places=2, default=3.00,
        help_text="Points per caused turnover"
    )
    scoring_blocked_shots = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.00,
        help_text="Points per blocked shot"
    )
    scoring_turnovers = models.DecimalField(
        max_digits=5, decimal_places=2, default=-1.00,
        help_text="Points per turnover (typically negative)"
    )
    
    # Goalie Scoring
    scoring_goalie_wins = models.DecimalField(
        max_digits=5, decimal_places=2, default=4.00,
        help_text="Points per goalie win"
    )
    scoring_goalie_saves = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00,
        help_text="Points per save"
    )
    scoring_goalie_goals_against = models.DecimalField(
        max_digits=5, decimal_places=2, default=-1.25,
        help_text="Points per goal against (typically negative)"
    )
    scoring_goalie_goals = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        help_text="Points per goalie goal"
    )
    scoring_goalie_assists = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.00,
        help_text="Points per goalie assist"
    )
    
    # Current week - the default week displayed to users
    current_week = models.ForeignKey(
        'Week',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leagues_current',
        help_text="The default week displayed to users (updated every Monday 9am PT)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.unique_id:
            self.unique_id = self.generate_unique_id()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_unique_id():
        """Generate a unique 8-character alphanumeric code"""
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(8))
            if not League.objects.filter(unique_id=code).exists():
                return code

    def __str__(self) -> str:
        return f"{self.name} (by {self.commissioner.username})"


class Team(models.Model):
    name = models.CharField(max_length=100)
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='teams',
        null=True,
        blank=True,
        help_text="The league this team belongs to"
    )
    waiver_priority = models.PositiveIntegerField(
        default=0,
        help_text="Lower number = higher priority. Resets to last when claim succeeds"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'league'],
                name='unique_team_name_per_league'
            )
        ]

    def __str__(self) -> str:
        if self.league:
            return f"{self.name} ({self.league.name})"
        return self.name
    
    def can_make_roster_changes(self, week=None):
        """
        Check if this team can currently make roster changes.
        If week is provided, checks if that specific week is unlocked.
        If week is not provided, finds the next unlocked week.
        Returns (can_change: bool, message: str, locked_until: date or None)
        """
        from django.utils import timezone
        
        if not self.league:
            return True, "No league restrictions", None
        
        league_season = self.league.created_at.year
        
        # If a specific week was provided, check if it's locked
        if week:
            if week.is_locked():
                lock_time = week.roster_lock_time
                if lock_time:
                    lock_time_pt = lock_time.astimezone(pytz.timezone('US/Pacific'))
                    return False, f"Week {week.week_number} is locked until after {lock_time_pt.strftime('%b %d at %I:%M %p %Z')}", None
                else:
                    return False, f"Week {week.week_number} is locked", None
            else:
                return True, f"Week {week.week_number} is unlocked", None
        
        # No specific week provided - find the next unlocked week
        all_weeks = Week.objects.filter(season=league_season).order_by('week_number')
        
        for w in all_weeks:
            if not w.is_locked():
                return True, f"Rosters unlocked for Week {w.week_number}", None
        
        # No unlocked weeks found
        return False, "All weeks are currently locked", None
    
    def is_over_roster_limit(self):
        """
        Check if this team is over the roster size limit.
        Returns the count of current roster players and whether they're over limit.
        """
        if not self.league:
            return 0, False
        
        current_count = Roster.objects.filter(
            team=self,
            week_dropped__isnull=True
        ).count()
        
        roster_limit = self.league.roster_size if hasattr(self.league, 'roster_size') else 14
        return current_count, current_count > roster_limit


class Roster(models.Model):
    """Manages player assignments to teams within specific leagues"""
    SLOT_CHOICES = [
        ('starter_o1', 'Starter Offense 1'),
        ('starter_o2', 'Starter Offense 2'),
        ('starter_o3', 'Starter Offense 3'),
        ('starter_d1', 'Starter Defense 1'),
        ('starter_d2', 'Starter Defense 2'),
        ('starter_d3', 'Starter Defense 3'),
        ('starter_g', 'Starter Goalie'),
        ('bench', 'Bench'),
    ]
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='roster_entries'
    )
    player = models.ForeignKey(
        'Player',  # Forward reference since Player is defined later
        on_delete=models.CASCADE,
        related_name='roster_entries'
    )
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='roster_entries',
        help_text="The league this roster assignment belongs to"
    )
    slot_assignment = models.CharField(
        max_length=20,
        choices=SLOT_CHOICES,
        default='bench',
        help_text="For traditional leagues: which slot this player is assigned to. For best ball leagues: always 'bench' (not used)"
    )
    added_date = models.DateTimeField(auto_now_add=True)
    week_added = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Week number when this player was added to the roster"
    )
    week_dropped = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Week number when this player was dropped from the roster (NULL if still active)"
    )

    class Meta:
        ordering = ['team', 'player']
        constraints = [
            models.UniqueConstraint(
                fields=['player', 'league'],
                name='unique_player_per_league',
                condition=models.Q(week_dropped__isnull=True)
            )
        ]
        indexes = [
            models.Index(fields=['team', 'league']),
            models.Index(fields=['player', 'league']),
            models.Index(fields=['week_added', 'week_dropped']),
        ]

    def __str__(self) -> str:
        return f"{self.player} on {self.team.name} ({self.league.name})"


class Player(models.Model):
    class Position(models.TextChoices):
        OFFENCE = "O", "Offence"
        DEFENCE = "D", "Defence"
        TRANSITION = "T", "Transition"
        GOALIE = "G", "Goalie"

    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text="Jersey number (0-99). Not required to be unique.",
        null=True,
        blank=True,
    )

    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50)

    position = models.CharField(max_length=1, choices=Position.choices)

    # NLL team the player belongs to (real-world team, not fantasy)
    nll_team = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="The actual NLL team this player plays for"
    )

    # Optional assigned side for fantasy lineup (e.g., Transition slotted as Offence or Defence)
    assigned_side = models.CharField(
        max_length=1,
        choices=Position.choices,
        null=True,
        blank=True,
        help_text="Override for lineup slot (use O or D for Transition players)",
    )

    external_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text="Unique ID from your source data (recommended for imports).",
    )

    # Player biography fields
    shoots = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="Handedness (Right/Left) or throws/catches hand"
    )
    height = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="Height (e.g., '6\\'2\\\"')"
    )
    weight = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Weight in pounds"
    )
    hometown = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Player's hometown"
    )
    draft_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Year player was drafted into NLL"
    )
    draft_team = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="NLL team that drafted the player"
    )
    birthdate = models.DateField(
        null=True,
        blank=True,
        help_text="Player's date of birth"
    )

    active = models.BooleanField(default=True)
    is_rookie = models.BooleanField(
        default=False,
        help_text="Whether the player is a rookie in the current season"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["position"]),
            models.Index(fields=["external_id"]),
        ]
        ordering = ["last_name", "first_name", "id"]

    def __str__(self) -> str:
        middle = f" {self.middle_name[0]}." if self.middle_name else ""
        num = f" #{self.number}" if self.number is not None else ""
        return f"{self.last_name}, {self.first_name}{middle}{num}"


class Week(models.Model):
    season = models.PositiveSmallIntegerField(help_text="e.g., 2026")
    week_number = models.PositiveSmallIntegerField(help_text="1..N within a season")

    start_date = models.DateField()
    end_date = models.DateField()
    
    # Roster lock/unlock times
    # Rosters lock permanently at first game time, unlock only during Mon 9am to first game window
    roster_lock_time = models.DateTimeField(
        null=True, blank=True,
        help_text="When rosters PERMANENTLY lock (time of first game - locked forever after this)"
    )
    roster_unlock_time = models.DateTimeField(
        null=True, blank=True,
        help_text="When rosters unlock (Monday 9am PT of same week - only unlocked until first game)"
    )
    
    is_playoff = models.BooleanField(
        default=False,
        help_text="True if this week contains NLL playoff games (not fantasy playoffs)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season", "week_number"], name="uniq_week_per_season"
            ),
        ]
        indexes = [
            models.Index(fields=["season", "week_number"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["season", "start_date"]),
        ]
        ordering = ["-season", "week_number"]

    def __str__(self) -> str:
        return f"{self.season} - Week {self.week_number} ({self.start_date} to {self.end_date})"
    
    def is_locked(self):
        """
        Returns True if roster transactions are locked for this week.
        
        Lock rules:
        - Once a week's first game starts (lock_time), it stays locked permanently
        - ALL weeks lock when any week is currently active (games in progress)
        - Weeks only unlock between Monday 9 AM and first game Friday
        """
        from django.utils import timezone
        
        now = timezone.now()
        
        # If lock/unlock times aren't set, fall back to old behavior (start_date based)
        if not self.roster_lock_time or not self.roster_unlock_time:
            if self.start_date <= now.date():
                return True
            return False
        
        # Rule 1: Once this week's first game starts, it stays locked permanently
        if now >= self.roster_lock_time:
            return True
        
        # Rule 2: Check if ANY week is currently active (first game started, but not past next week's unlock)
        # If any week is active, ALL weeks are locked
        league_season = self.season if hasattr(self, 'season') else self.start_date.year
        any_week_active = Week.objects.filter(
            season=league_season,
            roster_lock_time__lte=now,     # This week's games have started
            roster_unlock_time__gt=now     # But we're not yet at next week's unlock time
        ).exclude(id=self.id).exists()     # Exclude this week (we already checked above)
        
        if any_week_active:
            return True
        
        # Rule 3: No active weeks - check if this specific week's unlock window is open
        # (between Monday 9 AM and Friday first game)
        if self.roster_unlock_time <= now < self.roster_lock_time:
            return False
        
        # Before unlock_time: week is locked (future week hasn't opened yet)
        return True



# New Game model
class Game(models.Model):
    week = models.ForeignKey('Week', on_delete=models.CASCADE, related_name='games')
    date = models.DateField()
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    nll_game_id = models.CharField(max_length=32, blank=True, null=True, help_text="External NLL game ID if available")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "home_team", "away_team"]
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'home_team', 'away_team'],
                name='unique_game_per_date'
            )
        ]
        indexes = [
            models.Index(fields=['date', 'week']),
            models.Index(fields=['nll_game_id']),
        ]

    def __str__(self):
        return f"{self.date}: {self.home_team} vs {self.away_team}"


# Updated PlayerWeekStat to PlayerGameStat
class PlayerGameStat(models.Model):
    player = models.ForeignKey('Player', on_delete=models.CASCADE, related_name="game_stats")
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name="player_stats")

    goals = models.PositiveSmallIntegerField(default=0)
    assists = models.PositiveSmallIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)

    loose_balls = models.PositiveSmallIntegerField(default=0)
    turnovers = models.PositiveSmallIntegerField(default=0)
    caused_turnovers = models.PositiveSmallIntegerField(default=0)
    blocked_shots = models.PositiveSmallIntegerField(default=0)

    # Goalie-specific stats
    wins = models.PositiveSmallIntegerField(default=0, help_text="Goalie wins")
    saves = models.PositiveSmallIntegerField(default=0, help_text="Goalie saves")
    goals_against = models.PositiveSmallIntegerField(default=0, help_text="Goals allowed by goalie")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "game"], name="uniq_player_game_stat"
            ),
        ]
        indexes = [
            models.Index(fields=["game", "player"]),
            models.Index(fields=["player", "game"]),
        ]
        ordering = ["game__date", "player__last_name"]

    def __str__(self) -> str:
        return f"{self.player} - {self.game}"


class ImportRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    uploaded_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_runs",
    )

    uploaded_file = models.FileField(upload_to="imports/")
    original_filename = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    players_created = models.PositiveIntegerField(default=0)
    players_updated = models.PositiveIntegerField(default=0)
    weeks_created = models.PositiveIntegerField(default=0)
    weeks_updated = models.PositiveIntegerField(default=0)
    stats_created = models.PositiveIntegerField(default=0)
    stats_updated = models.PositiveIntegerField(default=0)

    log = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ImportRun {self.id} - {self.status} - {self.original_filename or self.uploaded_file.name}"


class FantasyTeamOwner(models.Model):
    """Links Django User accounts to fantasy Teams (for chat & ownership)"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fantasy_teams",
    )
    team = models.OneToOneField(
        Team,
        on_delete=models.CASCADE,
        related_name="owner",
        help_text="The fantasy team this user owns"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team__name"]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'team'],
                name='unique_user_team'
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username} owns {self.team.name}"


class ChatMessage(models.Model):
    """League chat messages and system notifications"""
    class MessageType(models.TextChoices):
        CHAT = "CHAT", "Chat Message"
        ADD = "ADD", "Player Added"
        DROP = "DROP", "Player Dropped"
        TRADE = "TRADE", "Trade"
        SYSTEM = "SYSTEM", "System Notification"

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        null=True,
        blank=True,
        help_text="The league this message belongs to"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
        help_text="User who sent the message (null for system messages)"
    )
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.CHAT
    )
    message = models.TextField()
    
    # For transaction notifications
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Player involved in add/drop/trade"
    )
    player_dropped = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dropped_transactions",
        help_text="Player dropped in a waiver/trade transaction"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Team involved in transaction"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["message_type"]),
        ]

    def __str__(self) -> str:
        sender_name = self.sender.username if self.sender else "System"
        return f"[{self.message_type}] {sender_name}: {self.message[:50]}"

class TeamChatMessage(models.Model):
    """Private messages between two teams"""
    class MessageType(models.TextChoices):
        CHAT = "CHAT", "Chat Message"
        TRADE_PROPOSED = "TRADE_PROPOSED", "Trade Proposed"
        TRADE_ACCEPTED = "TRADE_ACCEPTED", "Trade Accepted"
        TRADE_REJECTED = "TRADE_REJECTED", "Trade Rejected"
        TRADE_CANCELLED = "TRADE_CANCELLED", "Trade Cancelled"
        TRADE_EXECUTED = "TRADE_EXECUTED", "Trade Executed"
    
    team1 = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="team_chats_as_team1",
        help_text="First team in the conversation"
    )
    team2 = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="team_chats_as_team2",
        help_text="Second team in the conversation"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_chat_messages",
        help_text="User who sent the message"
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.CHAT
    )
    message = models.TextField()
    
    # Reference to related trade
    trade = models.ForeignKey(
        'Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
        help_text="Trade related to this message"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team1", "team2"]),
            models.Index(fields=["-created_at"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.team1.name} ↔ {self.team2.name}: {self.message[:50]}"

class WaiverClaim(models.Model):
    """Waiver claims for players that process when rosters unlock"""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESSFUL = "SUCCESSFUL", "Successful"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
    
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="waiver_claims",
        help_text="The league this claim belongs to"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="waiver_claims",
        help_text="Team making the claim"
    )
    player_to_add = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="waiver_claims_for",
        help_text="Player to add if claim is successful"
    )
    player_to_drop = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="waiver_claims_dropping",
        null=True,
        blank=True,
        help_text="Player to drop if claim is successful (null if roster has space)"
    )
    week = models.ForeignKey(
        'Week',
        on_delete=models.CASCADE,
        related_name="waiver_claims",
        help_text="Week when this claim was submitted"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Waiver priority snapshot at time of claim (lower is better)"
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this claim was processed"
    )
    failure_reason = models.TextField(
        blank=True,
        help_text="Why the claim failed (if applicable)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "created_at"]
        indexes = [
            models.Index(fields=["league", "status", "priority"]),
            models.Index(fields=["week", "status"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.team.name} claims {self.player_to_add} (Week {self.week.week_number})"


class Draft(models.Model):
    """Draft for a fantasy league"""
    class DraftOrderType(models.TextChoices):
        RANDOM = "RANDOM", "Random"
        MANUAL = "MANUAL", "Commissioner Selected"
    
    class DraftStyle(models.TextChoices):
        SNAKE = "SNAKE", "Snake Draft (1,2,3,4 then 4,3,2,1)"
        LINEAR = "LINEAR", "Linear Draft (1,2,3,4 every round)"
    
    league = models.OneToOneField(
        League,
        on_delete=models.CASCADE,
        related_name='draft',
        help_text="The league this draft belongs to"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether the draft is currently in progress"
    )
    completed = models.BooleanField(
        default=False,
        help_text="Whether the draft has been completed"
    )
    draft_order_type = models.CharField(
        max_length=10,
        choices=DraftOrderType.choices,
        default=DraftOrderType.RANDOM,
        help_text="How the draft order was determined"
    )
    draft_style = models.CharField(
        max_length=10,
        choices=DraftStyle.choices,
        default=DraftStyle.SNAKE,
        help_text="Draft pick order style"
    )
    current_round = models.PositiveSmallIntegerField(
        default=1,
        help_text="Current round number"
    )
    current_pick = models.PositiveSmallIntegerField(
        default=1,
        help_text="Current pick number within the round"
    )
    total_rounds = models.PositiveSmallIntegerField(
        default=12,
        help_text="Total number of rounds (should match league roster_size)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self) -> str:
        status = "Completed" if self.completed else ("Active" if self.is_active else "Not Started")
        return f"Draft for {self.league.name} ({status})"
    
    def get_draft_order(self):
        """Get the ordered list of teams for this draft"""
        return list(self.draft_positions.select_related('team').order_by('position'))
    
    def get_current_team(self):
        """Get the team that should pick next based on draft style"""
        if self.completed:
            return None
        
        teams = self.get_draft_order()
        num_teams = len(teams)
        
        if num_teams == 0:
            return None
        
        # Determine position based on draft style
        if self.draft_style == self.DraftStyle.SNAKE:
            # Snake draft: odd rounds go forward, even rounds go backward
            if self.current_round % 2 == 1:  # Odd round (1, 3, 5, ...)
                position = self.current_pick
            else:  # Even round (2, 4, 6, ...)
                position = num_teams - self.current_pick + 1
        else:  # LINEAR
            # Linear draft: same order every round
            position = self.current_pick
        
        # Find the team at this position
        for draft_pos in teams:
            if draft_pos.position == position:
                return draft_pos.team
        
        return None
    
    def advance_pick(self):
        """Move to the next pick"""
        teams = self.get_draft_order()
        num_teams = len(teams)
        
        if self.current_pick < num_teams:
            self.current_pick += 1
        else:
            # Move to next round
            self.current_round += 1
            self.current_pick = 1
            
            # Check if draft is complete
            if self.current_round > self.total_rounds:
                self.completed = True
                self.is_active = False
                from django.utils import timezone
                self.completed_at = timezone.now()
        
        self.save()


class DraftPosition(models.Model):
    """Defines the draft order for teams in a draft"""
    draft = models.ForeignKey(
        Draft,
        on_delete=models.CASCADE,
        related_name='draft_positions'
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='draft_positions'
    )
    position = models.PositiveSmallIntegerField(
        help_text="Draft position (1 = first pick)"
    )
    
    class Meta:
        ordering = ['draft', 'position']
        unique_together = [['draft', 'team'], ['draft', 'position']]
    
    def __str__(self) -> str:
        return f"{self.team.name} - Pick #{self.position} in {self.draft.league.name}"


class DraftPick(models.Model):
    """Individual draft pick record"""
    draft = models.ForeignKey(
        Draft,
        on_delete=models.CASCADE,
        related_name='picks'
    )
    round = models.PositiveSmallIntegerField(
        help_text="Round number"
    )
    pick_number = models.PositiveSmallIntegerField(
        help_text="Pick number within the round"
    )
    overall_pick = models.PositiveSmallIntegerField(
        help_text="Overall pick number in the draft"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='draft_picks'
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='draft_picks',
        null=True,
        blank=True,
        help_text="Player selected (null if not yet picked)"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['draft', 'overall_pick']
        unique_together = [['draft', 'round', 'pick_number']]
        indexes = [
            models.Index(fields=['draft', 'overall_pick']),
            models.Index(fields=['team', 'draft']),
        ]
    
    def __str__(self) -> str:
        player_name = self.player.get_full_name() if self.player else "TBD"
        return f"Round {self.round}, Pick {self.pick_number}: {self.team.name} - {player_name}"


class RookieDraft(models.Model):
    """Rookie-only draft for dynasty leagues held during season renewal"""
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='rookie_drafts',
        help_text="Dynasty league this rookie draft belongs to"
    )
    season_year = models.PositiveSmallIntegerField(
        help_text="Season year for which rookies are being drafted"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether the draft is currently in progress"
    )
    completed = models.BooleanField(
        default=False,
        help_text="Whether the draft has been completed"
    )
    draft_style = models.CharField(
        max_length=10,
        choices=[
            ("snake", "Snake Draft (1,2,3,4 then 4,3,2,1)"),
            ("linear", "Linear Draft (1,2,3,4 every round)"),
        ],
        default="snake",
        help_text="Draft pick order style"
    )
    current_round = models.PositiveSmallIntegerField(
        default=1,
        help_text="Current round number (1-2 for rookie drafts)"
    )
    current_pick = models.PositiveSmallIntegerField(
        default=1,
        help_text="Current pick number within the round"
    )
    order_locked = models.BooleanField(
        default=False,
        help_text="Whether draft order is locked (can't modify once locked)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-season_year', '-created_at']
        indexes = [
            models.Index(fields=['league', 'season_year']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self) -> str:
        status = "Active" if self.is_active else ("Completed" if self.completed else "Pending")
        return f"{self.league.name} - {self.season_year} Rookie Draft ({status})"


class RookieDraftPick(models.Model):
    """Individual rookie draft pick"""
    draft = models.ForeignKey(
        RookieDraft,
        on_delete=models.CASCADE,
        related_name='picks',
        help_text="Rookie draft this pick belongs to"
    )
    round = models.PositiveSmallIntegerField(
        help_text="Round number (1-2)"
    )
    pick_number = models.PositiveSmallIntegerField(
        help_text="Pick number within the round"
    )
    overall_pick = models.PositiveSmallIntegerField(
        help_text="Overall pick number in the draft"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='rookie_draft_picks',
        help_text="Team with this pick"
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        related_name='rookie_draft_picks',
        null=True,
        blank=True,
        help_text="Rookie player selected (null if not yet picked)"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['draft', 'overall_pick']
        unique_together = [['draft', 'round', 'pick_number']]
        indexes = [
            models.Index(fields=['draft', 'overall_pick']),
            models.Index(fields=['team', 'draft']),
        ]
    
    def __str__(self) -> str:
        player_name = self.player.get_full_name() if self.player else "TBD"
        return f"R{self.round}P{self.pick_number}: {self.team.name} - {player_name}"


class TaxiSquad(models.Model):
    """Taxi Squad slots for Dynasty leagues - holds rookie players that don't score"""
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='taxi_squad',
        help_text="Fantasy team this taxi squad belongs to"
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taxi_squad_entries',
        help_text="Rookie player in this taxi slot (null if empty)"
    )
    slot_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        help_text="Which taxi slot (1, 2, or 3)"
    )
    added_date = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(
        default=False,
        help_text="Whether this taxi squad slot is locked (season started)"
    )
    
    class Meta:
        ordering = ['team', 'slot_number']
        unique_together = [['team', 'player']]
        constraints = [
            models.UniqueConstraint(
                fields=['team', 'slot_number'],
                name='unique_taxi_slot_per_team'
            ),
            models.CheckConstraint(
                condition=models.Q(slot_number__in=[1, 2, 3]),
                name='taxi_slot_1_to_3'
            )
        ]
        indexes = [
            models.Index(fields=['team', 'is_locked']),
            models.Index(fields=['player']),
        ]
    
    def __str__(self) -> str:
        return f"{self.team.name} Taxi Slot {self.slot_number}: {self.player.get_full_name()}"


class Trade(models.Model):
    """Trade offer between two teams"""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    proposing_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='proposed_trades'
    )
    receiving_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='received_trades'
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was executed (players actually swapped)"
    )
    failure_reason = models.TextField(
        blank=True,
        help_text="Reason if trade execution failed"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was processed (executed or failed)"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['league', 'status']),
            models.Index(fields=['proposing_team', 'status']),
            models.Index(fields=['receiving_team', 'status']),
        ]
    
    def __str__(self) -> str:
        return f"Trade: {self.proposing_team.name} ↔ {self.receiving_team.name} ({self.status})"


class TradePlayer(models.Model):
    """Players included in a trade"""
    trade = models.ForeignKey(
        Trade,
        on_delete=models.CASCADE,
        related_name='players'
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE
    )
    from_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='+'
    )
    
    class Meta:
        unique_together = [['trade', 'player']]
    
    def __str__(self) -> str:
        return f"{self.player.get_full_name()} from {self.from_team.name}"


class BugReport(models.Model):
    """User-submitted bug reports for tracking and monitoring application issues"""
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('wontfix', 'Won\'t Fix'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    # User who reported the bug
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bug_reports'
    )
    
    # Bug details
    title = models.CharField(
        max_length=200,
        help_text="Brief summary of the issue"
    )
    description = models.TextField(
        help_text="Detailed description of the bug, steps to reproduce, etc."
    )
    
    # Severity and tracking
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='new'
    )
    
    # Context information
    page_url = models.URLField(
        blank=True,
        help_text="URL where the bug occurred"
    )
    browser_info = models.CharField(
        max_length=255,
        blank=True,
        help_text="Browser and OS information"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Any error messages displayed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the bug was resolved"
    )
    
    # Admin notes
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes from developers/admins"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['priority', 'status']),
        ]
    
    def __str__(self) -> str:
        return f"[{self.get_priority_display()}] {self.title}"
    
    def mark_resolved(self):
        """Mark bug as resolved with timestamp"""
        from django.utils import timezone
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.save()
