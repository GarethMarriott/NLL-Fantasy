from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm as DjangoPasswordResetForm, SetPasswordForm as DjangoSetPasswordForm
from django.contrib.auth.models import User
from .models import League, Team


class ImportWeeklyStatsForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV with player + week + stats rows."
    )


class ImportTeamsForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV with team and player rows (team, first_name, last_name, number, position, external_id)."
    )


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class LeagueCreateForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ['name', 'description', 'max_teams']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'max_teams': forms.Select(choices=[
                (4, '4 teams'),
                (6, '6 teams'),
                (8, '8 teams'),
                (10, '10 teams'),
                (12, '12 teams'),
            ]),
        }


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name']
        
    def __init__(self, *args, league=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.league = league
    
    def save(self, commit=True):
        team = super().save(commit=False)
        if self.league:
            team.league = self.league
        if commit:
            team.save()
        return team


class TeamSettingsForm(forms.ModelForm):
    """Form for team owner to update their team name"""
    class Meta:
        model = Team
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
        }


class LeagueSettingsForm(forms.ModelForm):
    """Form for commissioner to update league settings"""
    class Meta:
        model = League
        fields = [
            'name', 'description', 'max_teams', 'is_public', 'roster_size', 
            'roster_forwards', 'roster_defense', 'roster_goalies',
            'playoff_teams', 'playoff_reseed', 'use_waivers',
            'multigame_scoring',
            'scoring_goals', 'scoring_assists', 'scoring_loose_balls', 
            'scoring_caused_turnovers', 'scoring_blocked_shots', 'scoring_turnovers',
            'scoring_goalie_wins', 'scoring_goalie_saves', 'scoring_goalie_goals_against',
            'scoring_goalie_goals', 'scoring_goalie_assists'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'max_teams': forms.Select(choices=[
                (4, '4 teams'),
                (6, '6 teams'),
                (8, '8 teams'),
                (10, '10 teams'),
                (12, '12 teams'),
            ], attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'rounded'}),
            'roster_size': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'min': 6, 'max': 20}),
            'roster_forwards': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'min': 0, 'max': 20}),
            'roster_defense': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'min': 0, 'max': 20}),
            'roster_goalies': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'min': 0, 'max': 20}),
            'playoff_teams': forms.Select(choices=[
                (2, '2 teams'),
                (4, '4 teams'),
                (6, '6 teams'),
                (8, '8 teams'),
            ], attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'playoff_reseed': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'use_waivers': forms.CheckboxInput(attrs={'class': 'rounded'}),
            'multigame_scoring': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
            'scoring_goals': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_assists': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_loose_balls': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_caused_turnovers': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_blocked_shots': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_turnovers': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_goalie_wins': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_goalie_saves': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_goalie_goals_against': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_goalie_goals': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
            'scoring_goalie_assists': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'step': '0.25'}),
        }
        help_texts = {
            'multigame_scoring': "If a player plays multiple games in a week, use their highest single-game score (default) or the average of their games.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove playoff_weeks from form fields entirely
        if 'playoff_weeks' in self.fields:
            self.fields.pop('playoff_weeks')

# ===== Password Reset Forms =====

class PasswordResetForm(DjangoPasswordResetForm):
    """Custom password reset form with Tailwind styling"""
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
        })
    )


class SetPasswordForm(DjangoSetPasswordForm):
    """Custom set password form with Tailwind styling"""
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        })
    )
    new_password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
    )