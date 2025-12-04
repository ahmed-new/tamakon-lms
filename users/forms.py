# users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="البريد الإلكتروني", required=True)
    first_name = forms.CharField(label="الاسم الأول", required=False)
    last_name = forms.CharField(label="اسم العائلة", required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("هذا البريد مسجّل مسبقًا.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        # الدور الافتراضي طالب
        user.role = User.Roles.STUDENT
        if commit:
            user.save()
        return user
