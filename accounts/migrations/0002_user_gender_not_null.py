from django.db import migrations, models


def null_gender_to_empty(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(gender__isnull=True).update(gender="")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # Existing NULLs must become "" before the column is made NOT NULL.
        migrations.RunPython(null_gender_to_empty, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("male", "male"), ("female", "female")],
                default="",
                max_length=10,
            ),
        ),
    ]
