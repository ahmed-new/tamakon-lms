# learning/forms.py
from django import forms
from .models import Question , ContactMessage

class QuestionForm(forms.ModelForm):
    # واجهة إدخال سهلة عند النوع "جدول"
    table_title = forms.CharField(label="عنوان الجدول", required=False)
    columns_csv = forms.CharField(
        label="أعمدة الجدول (CSV)", required=False,
        help_text="مثال: الحساب,مدين,دائن",
    )
    rows_csv = forms.CharField(
        label="صفوف الجدول (سطر لكل صف، CSV)", required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="مثال:\nالصندوق,1000,0\nالأوراق الدائنة,0,300\nالمشتريات,500,0\nالإجمالي,1500,300",
    )
    table_note = forms.CharField(label="ملاحظة أسفل الجدول", required=False)

    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تعبئة الحقول المساعدة من table_json لو موجود
        if self.instance and self.instance.table_json:
            tbl = self.instance.table_json or {}
            self.fields["table_title"].initial = (tbl.get("title") or "")
            self.fields["table_note"].initial = (tbl.get("note") or "")
            cols = tbl.get("columns") or []
            rows = tbl.get("rows") or []
            self.fields["columns_csv"].initial = ",".join(str(c) for c in cols)
            self.fields["rows_csv"].initial = "\n".join(",".join(str(c) for c in r) for r in rows)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("type") == Question.QType.TABLE:
            # لو الـ JSON مش متعبّي يدويًا، استخدم الحقول المساعدة
            tbl = cleaned.get("table_json")
            cols_csv = (cleaned.get("columns_csv") or "").strip()
            rows_csv = (cleaned.get("rows_csv") or "").strip()
            title = (cleaned.get("table_title") or "").strip()
            note = (cleaned.get("table_note") or "").strip()

            if not tbl:
                if not (cols_csv and rows_csv):
                    raise forms.ValidationError("أدخل JSON للجدول أو عبّئ أعمدة وصفوف CSV.")
                columns = [c.strip() for c in cols_csv.split(",") if c.strip()]
                if not columns:
                    raise forms.ValidationError("أدخل أعمدة صحيحة (CSV).")

                rows = []
                for i, line in enumerate(rows_csv.splitlines(), start=1):
                    line = line.strip()
                    if not line:
                        continue
                    row = [c.strip() for c in line.split(",")]
                    if len(row) != len(columns):
                        raise forms.ValidationError(f"الصف رقم {i} لا يطابق عدد الأعمدة ({len(columns)}).")
                    rows.append(row)

                cleaned["table_json"] = {
                    "title": title or None,
                    "columns": columns,
                    "rows": rows,
                    "note": note or None,
                }
        return cleaned






class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "whatsapp", "subject", "message"]
        labels = {
            "name": "الاسم",
            "email": "البريد الإلكتروني",
            "whatsapp": "رقم واتساب (اختياري)",
            "subject": "العنوان / موضوع الرسالة",
            "message": "نص الرسالة",
        }
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6}),
        }

    # تنسيق بسيط لرقم الواتساب (اختياري)
    def clean_whatsapp(self):
        w = (self.cleaned_data.get("whatsapp") or "").strip()
        if not w:
            return w
        # سماح بـ + وأرقام فقط
        import re
        if not re.fullmatch(r"[0-9+]{6,20}", w):
            raise forms.ValidationError("صيغة رقم الواتساب غير صحيحة.")
        return w
