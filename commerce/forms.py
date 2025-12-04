# commerce/forms.py
from django import forms

class FreezeEnrollmentForm(forms.Form):
    days = forms.IntegerField(min_value=1, max_value=90, label="عدد الأيام")
    password = forms.CharField(widget=forms.PasswordInput, label="كلمة المرور")
