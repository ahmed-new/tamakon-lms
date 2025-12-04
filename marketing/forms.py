# marketing/forms.py
from django import forms
from ckeditor.widgets import CKEditorWidget  # لو هتستعمل django-ckeditor

class ComposeEmailForm(forms.Form):
    subject = forms.CharField(max_length=200, label="عنوان الرسالة (Subject)")
    body_html = forms.CharField(widget=CKEditorWidget(), label="المحتوى")
    body_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 8}), label="النص العادي (اختياري)")
