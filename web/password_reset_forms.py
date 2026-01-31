from django import forms
from django.contrib.auth.forms import SetPasswordForm, PasswordResetForm as DjangoPasswordResetForm


class PasswordResetForm(DjangoPasswordResetForm):
    """Custom password reset form"""
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
        })
    )


class SetPasswordForm(SetPasswordForm):
    """Custom set password form"""
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        })
    )
    new_password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
    )
