from django import forms
from django.contrib.auth.forms import UserCreationForm
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
