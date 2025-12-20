from django import forms


class ImportWeeklyStatsForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV with player + week + stats rows."
    )
