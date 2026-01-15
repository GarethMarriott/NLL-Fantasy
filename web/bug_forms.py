from django import forms
from .models import BugReport


class BugReportForm(forms.ModelForm):
    """Form for users to report bugs"""
    
    class Meta:
        model = BugReport
        fields = ['title', 'description', 'priority', 'page_url', 'browser_info', 'error_message']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Brief summary of the issue',
                'maxlength': '200'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Detailed description, steps to reproduce, expected vs actual behavior...',
                'rows': 6
            }),
            'priority': forms.Select(attrs={
                'class': 'form-control'
            }),
            'page_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., https://nll-fantasy.com/league/ABC123/',
                'required': False
            }),
            'browser_info': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Chrome 120 on Windows 11',
                'required': False
            }),
            'error_message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Any error messages you saw (optional)',
                'rows': 3,
                'required': False
            }),
        }
        help_texts = {
            'title': 'Keep it concise and descriptive',
            'description': 'The more details, the faster we can fix it!',
            'priority': 'How critical is this issue for you?',
        }


class BugReportFilterForm(forms.Form):
    """Form for filtering bug reports"""
    
    STATUS_FILTER_CHOICES = [
        ('', 'All Statuses'),
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
    ]
    
    PRIORITY_FILTER_CHOICES = [
        ('', 'All Priorities'),
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_FILTER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    priority = forms.ChoiceField(
        choices=PRIORITY_FILTER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search bug title or description...'
        })
    )
