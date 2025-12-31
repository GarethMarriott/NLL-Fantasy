from django import forms


class ImportWeeklyStatsForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV with player + week + stats rows."
    )


class ImportTeamsForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV with team and player rows (team, first_name, last_name, number, position, external_id)."
    )
